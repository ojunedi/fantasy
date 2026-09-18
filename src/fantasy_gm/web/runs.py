"""Agent runs: registry, worker threads, event buffers, single-flight.

Why a dedicated daemon thread rather than `run_in_threadpool`: a run takes
minutes, must outlive the request that started it, and must survive the client
disconnecting. Putting one in Starlette's shared 40-slot threadpool would also
starve every other sync handler on the site.

The event buffer, not the subscriber queue, is the source of truth. Every event
gets a sequence number, so a reload replays the backlog and reconnects from the
last id it saw, and nothing is dropped or duplicated in between.

Runs are intentionally not durable. The registry is capped at the 20 most recent
and lost on restart; the artifact that matters is the `DecisionRecord` in sqlite,
which is written before the run reports itself done.
"""
from __future__ import annotations

import asyncio
import threading
import traceback
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

MAX_RUNS = 20

RUNNING = "running"
DONE = "done"
ERROR = "error"
CANCELLED = "cancelled"


class RunCancelled(Exception):
    """Raised inside the worker by the emit adapter when cancel is requested."""


@dataclass
class Run:
    id: str
    week: int
    season: int
    team_id: str
    supervised: bool
    kind: str = "lineup"
    status: str = RUNNING
    events: list[dict] = field(default_factory=list)
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    loop: asyncio.AbstractEventLoop | None = None
    decision_id: str | None = None
    error: str | None = None
    cancel: threading.Event = field(default_factory=threading.Event)
    # The trade brief, straight off the form. Replaces `memo/interview.py`'s
    # `input()` prompts, which a web request obviously cannot use.
    brief: dict | None = None

    @property
    def is_live(self) -> bool:
        return self.status == RUNNING

    @property
    def last_seq(self) -> int:
        return self.events[-1]["seq"] if self.events else -1


class RunManager:
    """Registry of runs, one per (kind, week, season) at a time."""

    def __init__(self, max_runs: int = MAX_RUNS):
        self._lock = threading.Lock()
        self._runs: OrderedDict[str, Run] = OrderedDict()
        self._active: dict[tuple[str, int, int], str] = {}
        self._max_runs = max_runs

    # -- registry ---------------------------------------------------------

    def get(self, run_id: str) -> Run | None:
        with self._lock:
            return self._runs.get(run_id)

    def get_active(self, kind: str, week: int, season: int) -> Run | None:
        """The live run for this week, if there is one."""
        with self._lock:
            run_id = self._active.get((kind, week, season))
            run = self._runs.get(run_id) if run_id else None
            if run is not None and not run.is_live:
                self._active.pop((kind, week, season), None)
                return None
            return run

    def create(self, kind: str, week: int, season: int, team_id: str,
               supervised: bool, loop: asyncio.AbstractEventLoop | None = None,
               brief: dict | None = None) -> Run:
        run = Run(id=uuid.uuid4().hex[:12], week=week, season=season,
                  team_id=team_id, supervised=supervised, kind=kind, loop=loop,
                  brief=brief)
        with self._lock:
            self._runs[run.id] = run
            self._active[(kind, week, season)] = run.id
            while len(self._runs) > self._max_runs:
                old_id, old = self._runs.popitem(last=False)
                self._active = {k: v for k, v in self._active.items() if v != old_id}
        return run

    # -- events -----------------------------------------------------------

    def publish(self, run: Run, event: dict) -> dict:
        """Append an event, then wake every subscriber. Thread-safe.

        Called from the worker thread, so the queue put is bounced onto the
        event loop: an asyncio.Queue is not safe to touch from another thread.
        """
        with self._lock:
            event = {**event, "seq": len(run.events)}
            run.events.append(event)
            subscribers = list(run.subscribers)

        loop = run.loop
        if loop is not None:
            for q in subscribers:
                try:
                    loop.call_soon_threadsafe(q.put_nowait, event)
                except RuntimeError:       # loop already closed — reload will replay
                    pass
        return event

    def subscribe(self, run: Run, queue: asyncio.Queue, after_seq: int = -1) -> list[dict]:
        """Register a queue and return the backlog, atomically.

        Both happen under one lock, which is the whole point: otherwise an event
        published between the snapshot and the registration is lost, and one
        published during both is delivered twice.
        """
        with self._lock:
            run.subscribers.add(queue)
            return [e for e in run.events if e["seq"] > after_seq]

    def unsubscribe(self, run: Run, queue: asyncio.Queue) -> None:
        with self._lock:
            run.subscribers.discard(queue)

    # -- lifecycle --------------------------------------------------------

    def finish(self, run: Run, status: str, decision_id: str | None = None,
               error: str | None = None) -> None:
        with self._lock:
            run.status = status
            run.decision_id = decision_id
            run.error = error
            self._active.pop((run.kind, run.week, run.season), None)
        self.publish(run, {"kind": status, "decision_id": decision_id, "error": error})

    def start(self, run: Run, worker) -> None:
        """Run `worker(run)` on a daemon thread. Daemon so a Ctrl-C on uvicorn
        is not held hostage by an in-flight LLM call."""
        thread = threading.Thread(target=self._guard, args=(run, worker),
                                  name=f"run-{run.id}", daemon=True)
        thread.start()

    def _guard(self, run: Run, worker) -> None:
        try:
            decision_id = worker(run)
        except RunCancelled:
            self.finish(run, CANCELLED)
        except Exception as exc:
            self.finish(run, ERROR, error=f"{type(exc).__name__}: {exc}")
            traceback.print_exc()
        else:
            self.finish(run, DONE, decision_id=decision_id)

    def request_cancel(self, run: Run) -> None:
        run.cancel.set()


def lineup_worker(settings: Any, run: Run, manager: RunManager,
                  agent_factory=None) -> str | None:
    """Mirror of `cli.cmd_run_week`, minus the interactive approval.

    Everything here is constructed **inside the worker thread**: `db/store.py`
    opens sqlite without `check_same_thread=False`, so a store built on the event
    loop thread cannot legally be used here, and an httpx client is not worth
    sharing across threads either. Both are cheap to build.

    The record is saved before `done` is published — same order as
    `present_and_approve`, which also saves first and prompts second, so a
    client that reloads the instant it sees `done` always finds the record.
    """
    from fantasy_gm.agent.config import AgentConfig
    from fantasy_gm.agent.tools import LineupToolContext
    from fantasy_gm.db.store import DecisionStore
    from fantasy_gm.web.deps import build_adapter
    from fantasy_gm.web.trace import make_emit_adapter

    emit = make_emit_adapter(run, manager)

    adapter = build_adapter(settings)
    league = adapter.get_league_settings(season=run.season)

    ctx = LineupToolContext(
        adapter=adapter, settings=league, team_id=run.team_id,
        week=run.week, season=run.season,
    )

    if run.supervised:
        from fantasy_gm.agent.supervisor import GMSupervisor
        posture = GMSupervisor(adapter, league, run.team_id).posture(run.week, run.season)
        ctx.posture = posture.posture
        emit({"kind": "posture", "posture": posture.posture,
              "rationale": posture.rationale})

    if agent_factory is None:
        from fantasy_gm.agent.graph import LineupGraphAgent
        agent = LineupGraphAgent(AgentConfig())
    else:
        agent = agent_factory()

    record = agent.decide(ctx, emit=emit)

    DecisionStore(settings.db_path).save(record)
    return str(record.id)


def _preferences_from_brief(brief: dict | None):
    """Form fields -> `TradePreferences`.

    The CLI gathers these through `memo/interview.py`'s `input()` prompts, which
    a request handler cannot use. The four fields are identical, so the agent
    sees exactly the same directive object either way. An empty brief produces
    empty preferences, which the agent treats as "no constraints" — the same as
    skipping every interview question.
    """
    from fantasy_gm.agent.trade.preferences import TradePreferences
    from fantasy_gm.models import Position

    prefs = TradePreferences()
    if not brief:
        return prefs

    wanted = []
    for raw in brief.get("want_positions") or []:
        match = next((p for p in (Position.QB, Position.RB, Position.WR, Position.TE)
                      if p.value.lower() == str(raw).lower()), None)
        if match is not None:
            wanted.append(match)
    prefs.want_positions = wanted
    prefs.offerable_ids = [str(i) for i in (brief.get("offerable_ids") or [])]
    prefs.target_ids = [str(i) for i in (brief.get("target_ids") or [])]
    prefs.notes = (brief.get("notes") or "").strip()
    return prefs


def trade_worker(settings: Any, run: Run, manager: RunManager,
                 agent_factory=None) -> str | None:
    """Mirror of `cli.cmd_propose_trades`, minus the interactive parts.

    Same construction-inside-the-thread rules as `lineup_worker`: the adapter
    and the store are both built here, never handed across from the event loop.

    The supervisor posture is unconditional in the CLI; here it follows the
    form's checkbox, because it costs a read and the page offers the choice.
    """
    from fantasy_gm.agent.config import AgentConfig
    from fantasy_gm.agent.trade.tools import TradeToolContext
    from fantasy_gm.db.store import DecisionStore
    from fantasy_gm.web.deps import build_adapter
    from fantasy_gm.web.trace import make_emit_adapter

    emit = make_emit_adapter(run, manager)

    adapter = build_adapter(settings)
    league = adapter.get_league_settings(season=run.season)

    ctx = TradeToolContext(
        adapter=adapter, settings=league, team_id=run.team_id,
        week=run.week, season=run.season,
    )
    ctx.preferences = _preferences_from_brief(run.brief)
    if not ctx.preferences.is_empty():
        emit({"kind": "brief", "summary": _describe_brief(ctx)})

    if run.supervised:
        from fantasy_gm.agent.supervisor import GMSupervisor
        posture = GMSupervisor(adapter, league, run.team_id).posture(run.week, run.season)
        ctx.posture = posture.posture
        emit({"kind": "posture", "posture": posture.posture,
              "rationale": posture.rationale})

    if agent_factory is None:
        from fantasy_gm.agent.trade.graph import TradeGraphAgent
        agent = TradeGraphAgent(AgentConfig())
    else:
        agent = agent_factory()

    record = agent.decide(ctx, emit=emit)

    DecisionStore(settings.db_path).save(record)
    return str(record.id)


def _describe_brief(ctx: Any) -> str:
    """One line of what the manager asked for, for the trace."""
    try:
        from fantasy_gm.agent.trade.preferences import describe
        names = {pid: info["name"] for pid, info in ctx.player_index().items()}
        return describe(ctx.preferences, names).strip()
    except Exception:
        return "brief applied"
