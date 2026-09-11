"""
Trade-agent tool context.

`TradeToolContext` extends the shared `ToolContext` with everything a trade
decision needs: all league rosters, a blended rest-of-season value map, and the
nflverse-backed analytics (DvP matchup, schedule strength, usage) plus the two
LLM sub-agents (injury, news). Every tool is read/compute/propose only — a trade
can never auto-execute (ESPN requires the counterparty to accept).

Heavy inputs are lazily built and cached; each can also be *injected* via the
constructor so the graph tests run fully offline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from fantasy_gm.agent.base import ToolContext
from fantasy_gm.core.game_env import from_schedule_row  # noqa: F401  (available to tools)
from fantasy_gm.core.matchup import DvpCell, matchup_grade
from fantasy_gm.core.schedule import playoff_sos, rest_of_season_sos
from fantasy_gm.core.trade_value import (
    AssetValue,
    build_value_map,
    evaluate_trade_for_roster,
)
from fantasy_gm.core.usage import usage_summary
from fantasy_gm.models import Player, Position, Roster
from fantasy_gm.signals.collector import ESPN_PRO_TEAM_ABBR

TERMINAL_TOOLS = {"propose_trades", "abstain"}

# Base positions we value/scan (starters + flex feeders).
SCAN_POSITIONS = (Position.QB, Position.RB, Position.WR, Position.TE)


@dataclass
class TradeToolContext(ToolContext):
    terminal_tools: frozenset[str] = frozenset(TERMINAL_TOOLS)

    # Injectable / lazily-built caches (all default None → built on first use).
    _all_rosters: list[Roster] | None = None
    _value_map: dict[str, AssetValue] | None = None
    _weekly_proj: dict[str, float] | None = None
    _dvp_table: dict[tuple[str, Position], DvpCell] | None = None
    _schedule_rows: list[dict] | None = None
    _usage_by_gsis: dict[str, list[dict]] | None = None
    _id_map: Any | None = None
    _player_index: dict[str, dict] | None = None  # pid -> {player, position, team, name}

    # Sub-agent callables (injectable for tests).
    injury_fn: Callable[..., dict] | None = None
    news_fn: Callable[..., dict] | None = None

    # ---- lazy builders -------------------------------------------------

    def all_rosters(self) -> list[Roster]:
        if self._all_rosters is None:
            self._all_rosters = self.adapter.get_all_rosters(self.week, self.season)
        return self._all_rosters

    def id_map(self):
        if self._id_map is None:
            from fantasy_gm.signals.sources import nflverse as nv
            self._id_map = nv.build_id_map()
        return self._id_map

    def _weeks_remaining(self) -> int:
        last = max(self.settings.playoff_weeks) if self.settings.playoff_weeks else 17
        return max(1, last - self.week + 1)

    def player_index(self) -> dict[str, dict]:
        """pid -> {player, position, team (abbrev), name} across all rosters."""
        if self._player_index is None:
            idx: dict[str, dict] = {}
            for r in self.all_rosters():
                for rp in r.players:
                    pid = rp.player.platform_id
                    idx[pid] = {
                        "player": rp.player,
                        "position": rp.player.position,
                        "team": ESPN_PRO_TEAM_ABBR.get(str(rp.player.nfl_team), ""),
                        "name": rp.player.name,
                        "owner_team_id": r.team_id,
                        "owner_name": r.owner_name,
                    }
            self._player_index = idx
        return self._player_index

    def weekly_projections(self) -> dict[str, float]:
        """Blended weekly projection per player id (ESPN + Sleeper)."""
        if self._weekly_proj is not None:
            return self._weekly_proj
        from fantasy_gm.core.projection_engine import blend_projections
        espn = self.adapter.get_projections(week=self.week, season=self.season)
        sources = {"espn": espn}
        try:
            from fantasy_gm.signals.sources.sleeper_proj import get_sleeper_projections
            sleeper_raw = get_sleeper_projections(self.season, self.week)
            idm = self.id_map()
            # Map sleeper_id -> espn id via gsis.
            sleeper_by_espn: dict[str, float] = {}
            sleeper_to_gsis = {v: k for k, v in idm.gsis_to_sleeper.items()}
            for sid, pts in sleeper_raw.items():
                gsis = sleeper_to_gsis.get(sid)
                espn_id = idm.espn(gsis) if gsis else None
                if espn_id:
                    sleeper_by_espn[espn_id] = pts
            if sleeper_by_espn:
                sources["sleeper"] = sleeper_by_espn
        except Exception:
            pass
        blended = blend_projections(sources)
        self._weekly_proj = {pid: bp.mean for pid, bp in blended.items()}
        return self._weekly_proj

    def value_map(self) -> dict[str, AssetValue]:
        if self._value_map is None:
            weekly = self.weekly_projections()
            wr = self._weeks_remaining()
            idx = self.player_index()
            ros = {pid: weekly.get(pid, 0.0) * wr for pid in idx}
            positions = {pid: info["position"] for pid, info in idx.items()}
            self._value_map = build_value_map(ros, positions)
        return self._value_map

    def dvp_table(self):
        if self._dvp_table is None:
            from fantasy_gm.core.matchup import compute_dvp
            from fantasy_gm.signals.sources import nflverse as nv
            rows = nv.player_stat_rows(self.season, through_week=self.week - 1)
            self._dvp_table = compute_dvp(rows)
        return self._dvp_table

    def schedule_rows(self) -> list[dict]:
        if self._schedule_rows is None:
            from fantasy_gm.signals.sources import nflverse as nv
            self._schedule_rows = nv.schedule_rows(self.season)
        return self._schedule_rows

    def usage_rows(self, gsis: str) -> list[dict]:
        if self._usage_by_gsis is None:
            from fantasy_gm.signals.sources import nflverse as nv
            rows = nv.player_stat_rows(self.season, through_week=self.week - 1)
            grouped: dict[str, list[dict]] = {}
            for r in rows:
                grouped.setdefault(r["player_id"], []).append(r)
            self._usage_by_gsis = grouped
        return self._usage_by_gsis.get(gsis, [])

    # ---- helpers -------------------------------------------------------

    def _gsis_of(self, pid: str) -> str | None:
        return self.id_map().gsis(pid)

    def _team_starter_requirements(self) -> dict[Position, int]:
        req: dict[Position, int] = {}
        for s in self.settings.roster_slots:
            if not s.is_starter:
                continue
            if s.position in (Position.FLEX, Position.SUPER_FLEX):
                continue
            req[s.position] = req.get(s.position, 0) + 1
        return req

    def _replacement_baselines(self) -> dict[Position, float]:
        """League 'startable' value floor per position.

        Ranks every player's asset value at a position across the league and
        takes the value at the last league-wide starter slot (team_count ×
        required) as replacement level. Players above it count as startable
        depth, so surplus/need reflects quality, not just raw roster counts.
        """
        req = self._team_starter_requirements()
        vm = self.value_map()
        idx = self.player_index()
        baselines: dict[Position, float] = {}
        for pos in SCAN_POSITIONS:
            vals = sorted(
                (vm[pid].value for pid, info in idx.items()
                 if info["position"] == pos and pid in vm),
                reverse=True,
            )
            n_starters = self.settings.team_count * max(1, req.get(pos, 0))
            if not vals:
                baselines[pos] = 0.0
            elif n_starters - 1 < len(vals):
                baselines[pos] = vals[n_starters - 1]
            else:
                baselines[pos] = vals[-1]
        return baselines

    def roster_needs(self, roster: Roster) -> dict[Position, dict]:
        """Per-position startable depth vs. starter requirement for one team.

        'Startable' = players whose asset value clears the league replacement
        baseline for the position. surplus>0 = tradeable quality depth;
        surplus<0 = a genuine need.
        """
        req = self._team_starter_requirements()
        baselines = self._replacement_baselines()
        vm = self.value_map()
        needs: dict[Position, dict] = {}
        for pos in SCAN_POSITIONS:
            players = [rp.player for rp in roster.players if rp.player.position == pos]
            startable = sum(
                1 for p in players
                if p.platform_id in vm and vm[p.platform_id].value >= baselines[pos]
            )
            required = req.get(pos, 0)
            needs[pos] = {"count": len(players), "startable": startable,
                          "required": required, "surplus": startable - required}
        return needs

    # ---- tools ---------------------------------------------------------

    def _tool_get_my_roster(self, _: dict) -> str:
        lines = [f"My roster (team {self.team_id}):"]
        vm = self.value_map()
        for rp in self.roster().players:
            pid = rp.player.platform_id
            av = vm.get(pid)
            val = f"{av.value:.1f}" if av else "?"
            lines.append(f"  {pid} | {rp.player.name} ({rp.player.position.value}) "
                         f"| value={val} | status={rp.player.status.value}")
        return "\n".join(lines)

    def _tool_get_all_rosters(self, _: dict) -> str:
        lines = ["League rosters (by position):"]
        for r in self.all_rosters():
            tag = " (ME)" if r.team_id == self.team_id else ""
            lines.append(f"\nTeam {r.team_id}{tag} — {r.owner_name}:")
            for pos in SCAN_POSITIONS:
                names = [rp.player.name for rp in r.players if rp.player.position == pos]
                if names:
                    lines.append(f"  {pos.value}: {', '.join(names)}")
        return "\n".join(lines)

    def _tool_get_roster_needs(self, _: dict) -> str:
        lines = ["Roster needs / surplus per team (startable depth vs. requirement):"]
        for r in self.all_rosters():
            tag = " (ME)" if r.team_id == self.team_id else ""
            needs = self.roster_needs(r)
            parts = []
            for pos, n in needs.items():
                flag = "SURPLUS" if n["surplus"] > 0 else ("NEED" if n["surplus"] < 0 else "ok")
                parts.append(f"{pos.value}:{n['startable']}startable/{n['required']}req({flag})")
            lines.append(f"  Team {r.team_id}{tag} {r.owner_name}: " + " ".join(parts))
        return "\n".join(lines)

    def _tool_find_trade_targets(self, tool_input: dict) -> str:
        want = tool_input.get("want_position")
        offer = tool_input.get("offer_position")
        vm = self.value_map()
        my_roster = self.roster()
        my_needs = self.roster_needs(my_roster)

        want_positions = [Position(want)] if want else [
            p for p, n in my_needs.items() if n["surplus"] < 0]
        offer_positions = [Position(offer)] if offer else [
            p for p, n in my_needs.items() if n["surplus"] > 0]
        if not want_positions:
            want_positions = list(SCAN_POSITIONS)
        if not offer_positions:
            offer_positions = list(SCAN_POSITIONS)

        lines = [f"Trade-target scan (I want {[p.value for p in want_positions]}, "
                 f"can offer surplus at {[p.value for p in offer_positions]}):"]
        for r in self.all_rosters():
            if r.team_id == self.team_id:
                continue
            their_needs = self.roster_needs(r)
            # Positions where THEY have surplus and I want
            they_offer = [p for p in want_positions if their_needs.get(p, {}).get("surplus", 0) > 0]
            # Positions where THEY need and I have surplus → my leverage
            they_need = [p for p in offer_positions if their_needs.get(p, {}).get("surplus", 0) < 0]
            if not they_offer and not they_need:
                continue
            lines.append(f"\n  Team {r.team_id} ({r.owner_name}):")
            for p in they_offer:
                cands = sorted(
                    [rp.player for rp in r.players if rp.player.position == p],
                    key=lambda pl: -(vm[pl.platform_id].value if pl.platform_id in vm else 0.0),
                )[:3]
                if cands:
                    lines.append(f"    acquire {p.value}: " + ", ".join(
                        f"{c.name}({c.platform_id}, val "
                        f"{vm[c.platform_id].value:.0f})" for c in cands if c.platform_id in vm))
            if they_need:
                lines.append(f"    they NEED: {[p.value for p in they_need]} "
                             f"(your surplus is leverage)")
        if len(lines) == 1:
            lines.append("  No clear cross-roster fits from surplus/need alone.")
        return "\n".join(lines)

    def _tool_get_trade_value(self, tool_input: dict) -> str:
        ids = tool_input.get("player_ids", [])
        vm = self.value_map()
        idx = self.player_index()
        lines = ["Asset values (rest-of-season projection × positional scarcity):"]
        for pid in ids:
            av = vm.get(pid)
            info = idx.get(pid, {})
            if av is None:
                lines.append(f"  {pid}: no value (not found / no projection)")
                continue
            lines.append(f"  {pid} | {info.get('name', pid)} ({av.position.value}) "
                         f"| RoS={av.ros_points:.1f} × scarcity {av.scarcity:.2f} "
                         f"= value {av.value:.1f}")
        return "\n".join(lines)

    def _tool_evaluate_trade(self, tool_input: dict) -> str:
        send_ids = tool_input.get("send_player_ids", [])
        receive_ids = tool_input.get("receive_player_ids", [])
        vm = self.value_map()
        idx = self.player_index()
        weekly = self.weekly_projections()

        my_players = [rp.player for rp in self.roster().players]
        incoming = [idx[i]["player"] for i in receive_ids if i in idx]
        ev = evaluate_trade_for_roster(
            my_players, incoming, send_ids, receive_ids, vm, weekly, self.settings)

        def names(pids):
            return ", ".join(idx.get(p, {}).get("name", p) for p in pids)

        lines = [
            f"Trade evaluation (my perspective):",
            f"  SEND ({names(send_ids)}): value {ev.send_value:.1f}",
            f"  RECEIVE ({names(receive_ids)}): value {ev.receive_value:.1f}",
            f"  EV delta: {ev.ev_delta:+.1f} | fairness {ev.fairness:.2f} | verdict: {ev.verdict.upper()}",
        ]
        if ev.roster_impact:
            lines.append(
                f"  Starting-lineup impact this week: "
                f"{ev.roster_impact.before_total:.1f} → {ev.roster_impact.after_total:.1f} "
                f"({ev.roster_impact.delta:+.1f})")
        return "\n".join(lines)

    def _tool_get_matchup_analysis(self, tool_input: dict) -> str:
        pid = tool_input.get("player_id", "")
        week = int(tool_input.get("week", self.week))
        info = self.player_index().get(pid)
        if not info or not info["team"]:
            return f"No team info for player {pid}; cannot grade matchup."
        team, pos = info["team"], info["position"]
        opp = None
        for g in self.schedule_rows():
            if g.get("week") != week:
                continue
            if g.get("home_team") == team:
                opp = g.get("away_team")
            elif g.get("away_team") == team:
                opp = g.get("home_team")
        if opp is None:
            return f"{info['name']} ({team}) has no week-{week} game (bye?)."
        grade = matchup_grade(self.dvp_table(), opp, pos)
        if grade is None:
            return f"{info['name']} vs {opp}: no DvP data yet for {pos.value}."
        return (f"{info['name']} ({team} {pos.value}) vs {opp} in wk{week}: "
                f"grade {grade.grade} (allows {grade.ppg_allowed:.1f} to {pos.value}, "
                f"league avg {grade.league_avg:.1f}, ratio {grade.ratio:.2f}, score {grade.score:.0f}/100).")

    def _tool_get_schedule_strength(self, tool_input: dict) -> str:
        pid = tool_input.get("player_id", "")
        info = self.player_index().get(pid)
        if not info or not info["team"]:
            return f"No team info for player {pid}; cannot grade schedule."
        team, pos = info["team"], info["position"]
        ros = rest_of_season_sos(self.schedule_rows(), self.dvp_table(), team, pos, self.week)
        po = playoff_sos(self.schedule_rows(), self.dvp_table(), team, pos)
        po_detail = ", ".join(f"wk{w.week} vs {w.opponent}({w.grade})" for w in po.weeks)
        return (
            f"{info['name']} ({team} {pos.value}) schedule strength (higher = easier):\n"
            f"  Rest-of-season (wk{self.week}+): grade {ros.grade}, score {ros.score:.0f}/100 "
            f"over {len(ros.graded_weeks)} graded weeks.\n"
            f"  Playoff window (wks 15-17): grade {po.grade}, score {po.score:.0f}/100 — {po_detail}")

    def _tool_get_usage_trends(self, tool_input: dict) -> str:
        pid = tool_input.get("player_id", "")
        info = self.player_index().get(pid)
        gsis = self._gsis_of(pid)
        rows = self.usage_rows(gsis) if gsis else []
        if not rows:
            return f"No usage history found for player {pid}."
        prof = usage_summary(rows, player_id=pid)
        w3, w5 = prof.window(3), prof.window(5)
        name = info["name"] if info else pid
        return (
            f"{name} usage trends (volume trumps talent):\n"
            f"  L3: {w3.targets:.1f} tgt, {w3.carries:.1f} car, tgt-share {w3.target_share:.0%}, "
            f"air-yds-share {w3.air_yards_share:.0%}, opp-score {w3.opportunity_score:.0f}/100\n"
            f"  L5: opp-score {w5.opportunity_score:.0f}/100\n"
            f"  trend: {prof.trend.upper()}"
            + (" — BREAKOUT flag" if prof.breakout else ""))

    def _tool_get_injury_report(self, tool_input: dict) -> str:
        pid = tool_input.get("player_id", "")
        info = self.player_index().get(pid)
        if not info:
            return f"Player {pid} not found."
        player: Player = info["player"]
        from fantasy_gm.models import PlayerStatus
        if player.status == PlayerStatus.ACTIVE:
            return f"{player.name}: ACTIVE — no injury concern, LLM interpretation skipped."
        fn = self.injury_fn or _default_injury_fn
        result = fn(
            player_name=player.name,
            status=player.status.value,
            practice_participation=None,
            injury_description=None,
            snap_share_last3=None,
        )
        return (f"Injury read for {player.name}: availability_pct="
                f"{result.get('availability_pct')}, role_change={result.get('role_change_flag')}. "
                f"{result.get('note', '')}")

    def _tool_get_player_news(self, tool_input: dict) -> str:
        pid = tool_input.get("player_id", "")
        info = self.player_index().get(pid)
        if not info:
            return f"Player {pid} not found."
        fn = self.news_fn or _default_news_fn
        result = fn(player_name=info["name"])
        events = result.get("events", [])
        head = (f"News read for {info['name']}: net outlook "
                f"{result.get('net_outlook', 'neutral')}. {result.get('note', '')}")
        for e in events[:4]:
            head += f"\n  - [{e.get('type')}/{e.get('impact')}] {e.get('summary')}"
        return head

    def _tool_propose_trades(self, tool_input: dict) -> str:
        import json
        idx = self.player_index()
        enriched = dict(tool_input)
        for pkg in enriched.get("trades", []):
            pkg["send_names"] = [idx.get(i, {}).get("name", i) for i in pkg.get("send_player_ids", [])]
            pkg["receive_names"] = [idx.get(i, {}).get("name", i) for i in pkg.get("receive_player_ids", [])]
        return json.dumps(enriched)

    def _tool_abstain(self, tool_input: dict) -> str:
        import json
        return json.dumps(tool_input)


def _default_injury_fn(**kwargs) -> dict:
    from fantasy_gm.agent.subagents.injury import interpret_injury
    return interpret_injury(**kwargs)


def _default_news_fn(**kwargs) -> dict:
    from fantasy_gm.agent.subagents.news import interpret_news
    return interpret_news(**kwargs)
