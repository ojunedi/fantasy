"""Waiver wire scoring agent.

A linear pipeline, not a tool loop: gather → signal-validate → score →
brief-generate → brief-validate → store.save(). Only brief-generate calls the
model, once, the same single-shot shape as the injury and news sub-agents.

Budget: ≤3 LLM calls per run (NFR-04). Every model call goes through
`_BudgetedLLM`, which refuses a call past `AgentConfig.max_llm_calls` and
records how many were made on the decision record.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from fantasy_gm.models import (
    DecisionRecord,
    DecisionType,
    LeagueSettings,
    Signal,
    WaiverScanResult,
    WaiverScanState,
)

# Maximum age a signal may be before it is considered stale, per source name.
# A source with no entry here is treated as stale: a signal nobody has said how
# long to trust cannot be shown to be fresh (I-02). Callers may pass an override.
_DEFAULT_FRESHNESS_SECONDS: dict[str, float] = {
    "projections": 6 * 3600,
    "roster": 6 * 3600,
    "free_agents": 6 * 3600,
    "injury_report": 4 * 3600,
    "depth_chart": 12 * 3600,
    "vegas": 24 * 3600,
    "news": 2 * 3600,
}

# Clock skew tolerated before a future as-of timestamp counts as fabricated.
_FUTURE_TOLERANCE_SECONDS = 300


class SignalError(ValueError):
    """A signal failed provenance (I-01) or freshness (I-02) validation."""

    def __init__(self, code: str, signal_label: str, detail: str):
        self.code = code
        self.signal_label = signal_label
        super().__init__(f"{code}: signal '{signal_label}' {detail}")


class BriefIntegrityError(ValueError):
    """The brief quoted a number the analysis did not produce (I-26)."""


class LLMBudgetExceeded(RuntimeError):
    """A model call was attempted past the run's budget (NFR-04)."""


# ---------------------------------------------------------------------------
# Signal validation (I-01, I-02)
# ---------------------------------------------------------------------------

def validate_signals(
    signals: list[Signal],
    now: datetime | None = None,
    freshness: dict[str, float] | None = None,
) -> None:
    """Validate provenance and freshness for every signal in the bundle.

    Raises SignalError naming the failing signal on the first violation.
    A signal with no source is named by its position in the bundle, since it
    has no other name. No exception means every signal is provenanced and fresh.
    """
    now = now or datetime.now(tz=timezone.utc)
    thresholds = freshness if freshness is not None else _DEFAULT_FRESHNESS_SECONDS

    for i, sig in enumerate(signals, start=1):
        # I-01: a source identifier. The as-of timestamp is required by the
        # Signal model itself, so a signal without one cannot reach this point.
        if not sig.source or not sig.source.strip():
            raise SignalError("SIGNAL_MISSING_PROVENANCE", f"#{i}",
                              "has no source identifier")
        as_of = sig.as_of
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        age_seconds = (now - as_of).total_seconds()
        # I-01: a timestamp from the future is not a real as-of time.
        if age_seconds < -_FUTURE_TOLERANCE_SECONDS:
            raise SignalError("SIGNAL_MISSING_PROVENANCE", sig.source,
                              "has an as-of timestamp in the future")

        # I-02: age against the source's freshness threshold
        threshold = thresholds.get(sig.source)
        if threshold is None:
            raise SignalError("SIGNAL_STALE", sig.source,
                              "has no freshness threshold, so it cannot be shown to be fresh")
        if age_seconds > threshold:
            raise SignalError("SIGNAL_STALE", sig.source,
                              f"is {age_seconds:.0f}s old (threshold {threshold:.0f}s)")


# ---------------------------------------------------------------------------
# Scoring (I-06, I-28, I-29, I-30, I-17)
# ---------------------------------------------------------------------------

def score_candidates(
    candidates: list[dict],
    roster: list[dict],
    league_settings: LeagueSettings,
    week: int,
) -> WaiverScanResult:
    """Evaluate candidates against all three bars and return the analysis.

    Each candidate dict: {name, position, ros_value, tier_rank, startable_weeks,
    start_gap}. start_gap is the points short of my weakest starter at the
    position (0 when the candidate would start).
    Each roster entry dict: {name, position, ros_value}

    Closest miss (I-17): the candidate that cleared the most bars, then the one
    whose failing bar sits latest (relative → absolute → startability), then
    the smallest gap on that bar. Gaps are only compared within one bar, since
    points and rank spots do not share a unit.
    """
    position_worst: dict[str, float] = {}
    for player in roster:
        pos = player["position"]
        val = player.get("ros_value", 0.0)
        if pos not in position_worst or val < position_worst[pos]:
            position_worst[pos] = val

    tiers = startable_tiers(league_settings)

    best_candidate = None
    best_margin = float("-inf")
    closest_miss = None
    closest_miss_bar = None
    closest_miss_by = float("inf")
    closest_key: tuple | None = None

    for c in candidates:
        pos = c["position"]
        ros_value = c.get("ros_value", 0.0)
        startable_weeks = c.get("startable_weeks", 0)
        tier_rank = c.get("tier_rank", 9999)

        worst_rostered = position_worst.get(pos, 0.0)

        # I-06: relative bar
        clears_relative = ros_value > worst_rostered
        # I-28: absolute bar
        clears_absolute = tier_rank <= tiers.get(pos, 0)
        # I-30: startability (fully-available roster assumed)
        clears_startable = startable_weeks >= 1

        # I-29: all three required
        if clears_relative and clears_absolute and clears_startable:
            margin = ros_value - worst_rostered
            if margin > best_margin:
                best_margin = margin
                best_candidate = c
            continue

        # Track closest miss (I-17)
        if not clears_relative:
            miss_by, bar, bar_index = worst_rostered - ros_value, "relative", 0
        elif not clears_absolute:
            miss_by, bar, bar_index = tier_rank - tiers.get(pos, 0), "absolute", 1
        else:
            miss_by, bar, bar_index = c.get("start_gap", 0.0), "startability", 2
        cleared = clears_relative + clears_absolute + clears_startable

        key = (-cleared, -bar_index, miss_by)
        if closest_key is None or key < closest_key:
            closest_key = key
            closest_miss_by = miss_by
            closest_miss = c
            closest_miss_bar = bar

    if best_candidate:
        pos = best_candidate["position"]
        worst = position_worst.get(pos, 0.0)
        return WaiverScanResult(
            scan_state=WaiverScanState.RECOMMENDATION,
            candidate=best_candidate["name"],
            displaced_player=_find_worst_name(roster, pos),
            value_margin=round(best_candidate["ros_value"] - worst, 2),
            bars_cleared=["relative", "absolute", "startability"],
            candidate_value=best_candidate["ros_value"],
            displaced_value=worst,
            candidate_rank=best_candidate.get("tier_rank"),
            startable_tier=tiers.get(pos),
        )

    pos = closest_miss["position"] if closest_miss else None
    return WaiverScanResult(
        scan_state=WaiverScanState.NO_CANDIDATE,
        closest_miss=closest_miss["name"] if closest_miss else None,
        failed_bar=closest_miss_bar,
        failed_by=round(closest_miss_by, 2) if closest_miss_by < float("inf") else None,
        candidate_value=closest_miss.get("ros_value") if closest_miss else None,
        displaced_value=position_worst.get(pos) if pos else None,
        candidate_rank=closest_miss.get("tier_rank") if closest_miss else None,
        startable_tier=tiers.get(pos) if pos else None,
    )


def startable_tiers(league_settings: LeagueSettings) -> dict[str, int]:
    """League-wide startable tier per position: team_count × starters there (I-28)."""
    tiers: dict[str, int] = {}
    for slot in league_settings.roster_slots:
        if slot.is_starter:
            pos = slot.position.value
            tiers[pos] = tiers.get(pos, 0) + league_settings.team_count
    return tiers


def _find_worst_name(roster: list[dict], position: str) -> str | None:
    worst_val = float("inf")
    worst_name = None
    for p in roster:
        if p["position"] == position and p.get("ros_value", 0.0) < worst_val:
            worst_val = p.get("ros_value", 0.0)
            worst_name = p["name"]
    return worst_name


# ---------------------------------------------------------------------------
# Brief validation (I-26)
# ---------------------------------------------------------------------------

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def traceable_numbers(result: WaiverScanResult, week: int, season: int) -> set[float]:
    """Every number the analysis produced, plus the week and season it ran for."""
    values = [
        result.value_margin, result.failed_by, result.candidate_value,
        result.displaced_value, result.candidate_rank, result.startable_tier,
        week, season,
    ]
    return {round(float(v), 2) for v in values if v is not None}


def validate_brief(brief: str, result: WaiverScanResult, week: int, season: int) -> None:
    """Reject a brief that introduces a number not present in the analysis output.

    Numbers compare by value, so "12.50" traces to 12.5. Digits inside a label
    ("WR3", "5th") are numbers too and must trace like any other.
    Raises BriefIntegrityError on the first untraced number.
    """
    allowed = traceable_numbers(result, week, season)
    untraced = sorted({n for n in _NUMBER.findall(brief) if round(float(n), 2) not in allowed})
    if untraced:
        raise BriefIntegrityError(
            f"BRIEF_INTEGRITY_VIOLATION: brief contains numbers not in analysis: {untraced}"
        )


# ---------------------------------------------------------------------------
# LLM budget (NFR-04)
# ---------------------------------------------------------------------------

class _BudgetedLLM:
    """Wraps a chat model; counts calls and refuses any past the budget."""

    def __init__(self, llm: Any, budget: int):
        self._llm = llm
        self.budget = budget
        self.calls = 0

    def __call__(self, prompt: str) -> str:
        if self.calls >= self.budget:
            raise LLMBudgetExceeded(
                f"LLM_BUDGET_EXCEEDED: {self.calls} of {self.budget} calls already made"
            )
        self.calls += 1
        from fantasy_gm.agent.subagents.base import _message_text
        return _message_text(self._llm.invoke(prompt))


def _brief_prompt(result: WaiverScanResult, week: int, season: int) -> str:
    allowed = ", ".join(_fmt(n) for n in sorted(traceable_numbers(result, week, season)))
    return (
        "Write a two-sentence waiver brief for a fantasy football manager.\n"
        f"Recommendation: add {result.candidate}, displacing {result.displaced_player}.\n"
        f"{result.candidate} projects {_fmt(result.candidate_value)} points, "
        f"{result.displaced_player} projects {_fmt(result.displaced_value)}, "
        f"a margin of {_fmt(result.value_margin)}. "
        f"{result.candidate} ranks {result.candidate_rank} at the position; "
        f"the league starts {result.startable_tier} there. Week {week}, {season} season.\n"
        f"Quote only these numbers, exactly: {allowed}. Do not write any other digit."
    )


def _fmt(n: float | int | None) -> str:
    if n is None:
        return "?"
    return str(int(n)) if float(n).is_integer() else f"{n:g}"


# ---------------------------------------------------------------------------
# Full agent run
# ---------------------------------------------------------------------------

def run_waiver_scan(
    store,
    week: int,
    season: int,
    settings: LeagueSettings,
    candidates: list[dict],
    roster: list[dict],
    signals: list[Signal],
    llm: Any | None = None,
    llm_budget: int | None = None,
    now: datetime | None = None,
    freshness: dict[str, float] | None = None,
    scorer=None,
) -> WaiverScanResult:
    """Run the full waiver scan pipeline.

    Writes a DecisionRecord to the store before returning or raising (NFR-10),
    for every outcome — recommendation, no-add, stale, provenance failure and
    brief rejection alike (I-19).

    `llm` is a chat model (anything with `.invoke(prompt)`); None means no brief
    is written. `scorer` defaults to `score_candidates` and is injectable so a
    test can prove a halted run never reached it.
    """
    now = now or datetime.now(tz=timezone.utc)
    scorer = scorer or score_candidates
    if llm_budget is None:
        from fantasy_gm.agent.config import AgentConfig
        llm_budget = AgentConfig().max_llm_calls
    budgeted = _BudgetedLLM(llm, llm_budget) if llm is not None else None

    def _calls() -> int:
        return budgeted.calls if budgeted else 0

    # Node 1: signal validation (I-01, I-02) — before anything is scored
    try:
        validate_signals(signals, now=now, freshness=freshness)
    except SignalError as exc:
        scan_state = (WaiverScanState.PROVENANCE_ERROR
                      if exc.code == "SIGNAL_MISSING_PROVENANCE"
                      else WaiverScanState.STALE)
        result = WaiverScanResult(scan_state=scan_state, failing_source=exc.signal_label)
        _write_record(store, week, season, result, signals, now,
                      llm_calls=0, error=str(exc))
        return result

    # Node 2: scoring (I-06, I-28, I-29, I-30, I-17)
    result = scorer(candidates, roster, settings, week)

    # Node 3: brief generation — the run's only model call. With no budget left
    # the recommendation stands without a brief rather than overspending.
    brief = ""
    brief_error: str | None = None
    if (result.scan_state == WaiverScanState.RECOMMENDATION
            and budgeted is not None and budgeted.calls < budgeted.budget):
        try:
            brief = budgeted(_brief_prompt(result, week, season))
        except Exception as exc:  # provider down, key revoked — the analysis still stands
            brief_error = f"BRIEF_UNAVAILABLE: {type(exc).__name__}: {exc}"
        # Node 4: brief validation (I-26). A rejected brief withholds the
        # recommendation, but the outcome is still logged before the run fails.
        try:
            validate_brief(brief, result, week, season)
        except BriefIntegrityError as exc:
            rejected = result.model_copy(update={"scan_state": WaiverScanState.BRIEF_REJECTED})
            _write_record(store, week, season, rejected, signals, now,
                          llm_calls=_calls(), error=str(exc), memo=brief)
            raise

    # Write decision record before reporting completion (NFR-10, I-19)
    _write_record(store, week, season, result, signals, now,
                  llm_calls=_calls(), error=brief_error, memo=brief)
    return result


def _write_record(store, week: int, season: int, result: WaiverScanResult,
                  signals: list[Signal], now: datetime, llm_calls: int,
                  error: str | None = None, memo: str = "") -> None:
    snapshot: dict[str, Any] = {"scan_state": result.scan_state.value, "llm_calls": llm_calls}
    if error:
        snapshot["error"] = error
    record = DecisionRecord(
        week=week,
        season=season,
        decision_type=DecisionType.WAIVER,
        inputs_snapshot=snapshot,
        signals_staleness=_staleness(signals, now),
        recommendation=result.model_dump(),
        memo=memo,
        confidence=1.0 if result.scan_state == WaiverScanState.RECOMMENDATION else 0.0,
    )
    store.save(record)


def _staleness(signals: list[Signal], now: datetime) -> dict[str, float]:
    out: dict[str, float] = {}
    for sig in signals:
        if not sig.source:
            continue
        as_of = sig.as_of if sig.as_of.tzinfo else sig.as_of.replace(tzinfo=timezone.utc)
        out[sig.source] = round((now - as_of).total_seconds(), 1)
    return out


# ---------------------------------------------------------------------------
# Inputs from the platform
# ---------------------------------------------------------------------------

def gather_scan_inputs(adapter, team_id: str, week: int, season: int,
                       league: LeagueSettings,
                       now: datetime | None = None) -> tuple[list[dict], list[dict], list[Signal]]:
    """Build the roster, candidates and signal bundle from the platform.

    Values are ESPN's rest-of-season projected points per game, from the same
    projections read the lineup agent uses. Per game, so a bye or a short
    absence does not lower a player's value — the bars compare against a fully
    available roster (I-30):
      - ros_value:       rest-of-season projected points per game
      - tier_rank:       rank by that value among every projected player at
                         the position, league-wide (1 = best)
      - startable_weeks: 1 if the candidate would start on a fully available
                         roster (beats my N-th best at the position, N = my
                         starting slots there), else 0. A per-game rate does
                         not vary week to week, so starting now stands for
                         starting within the three-week window.
      - start_gap:       points per game short of that N-th best (0 if starts)

    A rostered player ESPN has no projection for counts as 0.0 — still on the
    roster, still displaceable. Each read becomes a Signal stamped with when
    its data was fetched.
    """
    from fantasy_gm.adapters.espn import PROJECTIONS_FILTER_HEADERS

    now = now or datetime.now(tz=timezone.utc)

    my_roster = adapter.get_roster(team_id, week, season, fresh=True)
    roster_at = now
    free_agents = adapter.get_free_agents(week, season, fresh=True)
    fa_at = now
    projections = adapter.get_ros_projections(week, season)
    proj_at = _cached_at(adapter, season,
                         {"view": "kona_player_info", "scoringPeriodId": week},
                         PROJECTIONS_FILTER_HEADERS) or now

    by_id = {p.player_id: p for p in projections}

    # Positional rank across every projected player
    ranks: dict[str, int] = {}
    by_pos: dict[str, list] = {}
    for p in projections:
        by_pos.setdefault(p.position.value, []).append(p)
    for plist in by_pos.values():
        plist.sort(key=lambda p: p.projected_points, reverse=True)
        for i, p in enumerate(plist, start=1):
            ranks[p.player_id] = i

    roster = []
    for rp in my_roster.players:
        proj = by_id.get(rp.player.platform_id)
        roster.append({
            "name": rp.player.name,
            "position": rp.player.position.value,
            "ros_value": proj.projected_points if proj else 0.0,
        })

    my_starter_slots: dict[str, int] = {}
    for slot in league.roster_slots:
        if slot.is_starter:
            my_starter_slots[slot.position.value] = my_starter_slots.get(slot.position.value, 0) + 1

    candidates = []
    for fa in free_agents:
        pid = fa.player.platform_id
        proj = by_id.get(pid)
        if proj is None:
            continue  # no projection, nothing to score against
        pos = fa.player.position.value
        value = proj.projected_points
        mine = sorted((r["ros_value"] for r in roster if r["position"] == pos), reverse=True)
        n = my_starter_slots.get(pos, 0)
        if n == 0:
            starts, gap = False, value  # the position is never started
        elif len(mine) < n:
            starts, gap = True, 0.0     # an open starting slot
        else:
            starts = value > mine[n - 1]
            gap = 0.0 if starts else round(mine[n - 1] - value, 2)
        candidates.append({
            "name": fa.player.name,
            "position": pos,
            "ros_value": value,
            "tier_rank": ranks.get(pid, 9999),
            "startable_weeks": 1 if starts else 0,
            "start_gap": gap,
        })

    signals = [
        Signal(source="roster", as_of=roster_at, value=len(roster)),
        Signal(source="free_agents", as_of=fa_at, value=len(candidates)),
        Signal(source="projections", as_of=proj_at, value=len(projections)),
    ]
    return roster, candidates, signals


def _cached_at(adapter, season: int, params: dict, headers: dict) -> datetime | None:
    """When ESPN's projections were actually fetched, if served from cache."""
    from fantasy_gm.adapters.espn import cache_key
    try:
        stamp = adapter._cache.get_cached_at(cache_key(season, adapter.league_id, params, headers))
    except AttributeError:
        return None
    return datetime.fromtimestamp(stamp, tz=timezone.utc) if stamp else None
