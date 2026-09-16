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

# A position is only a real NEED when the best body you roster there is well
# below startable — not merely under the line. The replacement baseline is the
# last league-wide starter, so at a deep position (QB in a 1-QB league) half the
# league sits just under it while still starting someone perfectly fine every
# week. Requiring a material gap stops "my QB is 15th instead of 12th" from
# being reported the same as "my only QB is worthless".
_NEED_RATIO = 0.6

# Same reasoning one step milder for "thin". `best < bar` on its own flags a
# position the moment it is one rank under the last league-wide starter, which
# in a 1-QB league is true for over half the league by construction — pure
# noise. A material gap is required before the label means anything.
_THIN_RATIO = 0.85


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

    # Sub-agent callables (injectable for tests). Both are BATCH calls: they
    # take a list of players and return a dict keyed by player name, so a whole
    # batch costs one model call instead of one per player.
    injury_fn: Callable[..., dict[str, dict]] | None = None
    news_fn: Callable[..., dict[str, dict]] | None = None
    # Market-value fetch (FantasyCalc); injectable for offline tests.
    market_fn: Callable[..., dict] | None = None
    # Optional manager directives from the pre-run interview. None = unconstrained.
    preferences: Any = None
    # Every package `evaluate_trade` priced, in structured form, deduplicated.
    # The scoring is deterministic, so this is enough to pick a recommendation
    # WITHOUT the model: see `acceptable_packages`.
    evaluations: list[dict] = field(default_factory=list)

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

    def name_map(self) -> dict[str, str]:
        """pid -> display name, for the preference/violation helpers."""
        return {pid: info["name"] for pid, info in self.player_index().items()}

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

    def _market_values(self) -> dict:
        """FantasyCalc market values for this league format ({} on failure)."""
        num_qbs = sum(
            1 for s in self.settings.roster_slots
            if s.is_starter and s.position in (Position.QB, Position.SUPER_FLEX)
        )
        fn = self.market_fn
        if fn is None:
            from fantasy_gm.signals.sources.fantasycalc import get_market_values
            fn = get_market_values
        return fn(num_qbs=max(1, num_qbs), num_teams=self.settings.team_count, ppr=1.0)

    def value_map(self) -> dict[str, AssetValue]:
        if self._value_map is not None:
            return self._value_map
        weekly = self.weekly_projections()
        wr = self._weeks_remaining()
        idx = self.player_index()

        market = self._market_values()
        if market:
            # Market value is the trade currency. A player absent from the market
            # list is waiver/replacement level (value 0) for trade purposes.
            vm: dict[str, AssetValue] = {}
            for pid, info in idx.items():
                ros_val = round(weekly.get(pid, 0.0) * wr, 2)
                mv = market.get(pid)
                if mv is not None:
                    value, source, note = round(mv.value, 1), "market", f"{mv.position}{mv.position_rank}"
                else:
                    value, source, note = 0.0, "unranked", "not in FantasyCalc top values"
                vm[pid] = AssetValue(pid, info["position"], ros_points=ros_val,
                                     scarcity=1.0, value=value, source=source, note=note)
            self._value_map = vm
        else:
            # FantasyCalc unavailable → in-house ros×scarcity model.
            ros = {pid: round(weekly.get(pid, 0.0) * wr, 2) for pid in idx}
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

    def _flex_slots(self) -> int:
        return sum(1 for s in self.settings.roster_slots
                   if s.is_starter and s.position in (Position.FLEX, Position.SUPER_FLEX))

    def _flex_eligible(self) -> set[Position]:
        """Positions that can fill this league's flex slots."""
        from fantasy_gm.core.roster import FLEX_ELIGIBLE, SUPER_FLEX_ELIGIBLE
        elig: set[Position] = set()
        for s in self.settings.roster_slots:
            if not s.is_starter:
                continue
            if s.position == Position.FLEX:
                elig |= FLEX_ELIGIBLE
            elif s.position == Position.SUPER_FLEX:
                elig |= SUPER_FLEX_ELIGIBLE
        return {p for p in elig if p in SCAN_POSITIONS}

    def _replacement_baselines(self) -> dict[Position, float]:
        """League 'startable' value floor per position.

        Ranks every player's asset value at a position across the league and
        takes the value at the last league-wide starter slot as replacement
        level. Flex slots count too — ignoring them sets the RB/WR/TE bar far
        too high. They are split evenly across the flex-eligible positions,
        which is an approximation but much closer than dropping them.
        """
        req = self._team_starter_requirements()
        elig = self._flex_eligible()
        flex_share = (self._flex_slots() / len(elig)) if elig else 0.0
        vm = self.value_map()
        idx = self.player_index()
        baselines: dict[Position, float] = {}
        for pos in SCAN_POSITIONS:
            vals = sorted(
                (vm[pid].value for pid, info in idx.items()
                 if info["position"] == pos and pid in vm),
                reverse=True,
            )
            per_team = req.get(pos, 0) + (flex_share if pos in elig else 0.0)
            n_starters = max(1, round(self.settings.team_count * per_team))
            if not vals:
                baselines[pos] = 0.0
            elif n_starters - 1 < len(vals):
                baselines[pos] = vals[n_starters - 1]
            else:
                baselines[pos] = vals[-1]
        return baselines

    def trade_chips(self, roster: Roster) -> list[tuple]:
        """Players beyond a team's actual starting allocation that still carry
        market value — what that team can realistically trade away.

        Distinct from `roster_needs`: a chip does NOT have to clear the league
        replacement baseline. A backup QB or a WR4 is a real asset even though
        he is not a startable-quality piece, and the surplus math hides him.

        Returns [(RosterPlayer, AssetValue)] sorted by value, most valuable first.
        """
        req = self._team_starter_requirements()
        elig = self._flex_eligible()
        vm = self.value_map()

        def val(rp) -> float:
            av = vm.get(rp.player.platform_id)
            return av.value if av else 0.0

        by_pos: dict[Position, list] = {}
        for rp in roster.players:
            if rp.player.position in SCAN_POSITIONS:
                by_pos.setdefault(rp.player.position, []).append(rp)
        for players in by_pos.values():
            players.sort(key=lambda rp: -val(rp))

        locked: set[str] = set()
        flex_pool: list = []
        for pos, players in by_pos.items():
            n = req.get(pos, 0)
            for i, rp in enumerate(players):
                if i < n:
                    locked.add(rp.player.platform_id)
                elif pos in elig:
                    flex_pool.append(rp)

        # Flex slots go to the best remaining flex-eligible players.
        flex_pool.sort(key=lambda rp: -val(rp))
        for rp in flex_pool[:self._flex_slots()]:
            locked.add(rp.player.platform_id)

        chips = [
            (rp, vm[rp.player.platform_id])
            for players in by_pos.values() for rp in players
            if rp.player.platform_id not in locked
            and rp.player.platform_id in vm
            and vm[rp.player.platform_id].value > 0
        ]
        chips.sort(key=lambda t: -t[1].value)
        return chips

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
            bar = baselines[pos]
            startable = sum(
                1 for p in players
                if p.platform_id in vm and vm[p.platform_id].value >= bar
            )
            required = req.get(pos, 0)
            vals = sorted((vm[p.platform_id].value for p in players
                           if p.platform_id in vm), reverse=True)
            best = vals[0] if vals else 0.0
            # Bodies available to fill the slots, independent of quality. This is
            # the difference between "I have no QB" and "my QB is mediocre", and
            # conflating them is what produced the phantom QB crisis: `startable`
            # counts players clearing the LAST LEAGUE-WIDE STARTER's value, so in
            # a 1-QB league only 12 of ~19 rostered QBs can ever clear it and the
            # other teams reported "0 startable" while starting a QB every week.
            unfilled = max(0, required - len(players))
            # A real need: an actually empty slot, or the best body materially
            # below startable. Merely sitting under the bar is "thin".
            need = required > 0 and (unfilled > 0 or best < bar * _NEED_RATIO)
            thin = required > 0 and not need and best < bar * _THIN_RATIO
            needs[pos] = {"count": len(players), "startable": startable,
                          "required": required, "surplus": startable - required,
                          "filled": min(len(players), required), "unfilled": unfilled,
                          "best": best, "bar": bar, "need": need, "thin": thin}
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
        lines = [
            "Roster needs / surplus per team.",
            "READ THIS CAREFULLY: 'filled' counts bodies against required starter "
            "slots. 1/1 filled means the slot IS covered every week — that is NOT "
            "a hole and NOT a crisis, however low the value. 'thin' means the "
            "starter is below league-average quality: an UPGRADE opportunity, not "
            "a shortage. Only NEED means the position actually needs addressing.",
        ]
        for r in self.all_rosters():
            tag = " (ME)" if r.team_id == self.team_id else ""
            needs = self.roster_needs(r)
            parts = []
            for pos, n in needs.items():
                if n["need"]:
                    flag = "NEED"
                elif n["thin"]:
                    flag = "thin"
                elif n["surplus"] > 0:
                    flag = "SURPLUS"
                else:
                    flag = "ok"
                # Bodies-vs-slots first, then quality. Leading with the old
                # "0startable/1req" read as an empty slot to the model.
                parts.append(f"{pos.value}:{n['filled']}/{n['required']}filled"
                             f",best{n['best']:.0f}vs{n['bar']:.0f}bar({flag})")
            lines.append(f"  Team {r.team_id}{tag} {r.owner_name}: " + " ".join(parts))

        mine = self.trade_chips(self.roster())
        lines.append(
            "\nMY TRADEABLE DEPTH (players beyond my starting lineup, incl. bench — "
            "these are what I can realistically give up, even though they do not "
            "clear the startable baseline):"
        )
        if mine:
            for rp, av in mine:
                slot = "starter" if rp.is_starter else "bench"
                lines.append(f"  {rp.player.platform_id} | {rp.player.name} "
                             f"({rp.player.position.value}, {slot}) | value {av.value:.0f}")
        else:
            lines.append("  (none — every rostered asset is needed to fill a starting slot)")
        return "\n".join(lines)

    def _tool_find_trade_targets(self, tool_input: dict) -> str:
        want = tool_input.get("want_position")
        offer = tool_input.get("offer_position")
        my_roster = self.roster()
        my_needs = self.roster_needs(my_roster)
        my_chips = self.trade_chips(my_roster)

        prefs = self.preferences
        # Manager directives win over the computed scan; an explicit tool
        # argument wins over both.
        pref_wants = list(getattr(prefs, "want_positions", []) or [])
        if getattr(prefs, "offerable_ids", None):
            allowed = set(prefs.offerable_ids)
            my_chips = [(rp, av) for rp, av in my_chips
                        if rp.player.platform_id in allowed]

        want_positions = [Position(want)] if want else (pref_wants or [
            p for p, n in my_needs.items() if n["need"]])
        chip_positions: list[Position] = []
        for rp, _ in my_chips:
            if rp.player.position not in chip_positions:
                chip_positions.append(rp.player.position)
        offer_positions = [Position(offer)] if offer else chip_positions

        want_note = ""
        if not want_positions:
            want_positions = list(SCAN_POSITIONS)
            want_note = " (no clear need — scanning all)"
        elif pref_wants and not want:
            want_note = " (manager directive)"
        offer_note = ""
        if not offer_positions:
            offer_positions = list(SCAN_POSITIONS)
            offer_note = " (no tradeable depth — scanning all)"
        elif getattr(prefs, "offerable_ids", None) and not offer:
            offer_note = " (limited to the players you offered)"

        lines = [f"Trade-target scan. I want {[p.value for p in want_positions]}{want_note}; "
                 f"I can offer from {[p.value for p in offer_positions]}{offer_note}."]
        if my_chips:
            top = ", ".join(f"{rp.player.name} ({rp.player.position.value} {av.value:.0f})"
                            for rp, av in my_chips[:4])
            lines.append(f"  My best chips: {top}")

        # Targets the manager named explicitly — surfaced whatever position they
        # play, so a want-position filter cannot hide them.
        targets = list(getattr(prefs, "target_ids", []) or [])
        if targets:
            vm = self.value_map()
            idx = self.player_index()
            for pid in targets:
                info = idx.get(pid)
                if not info:
                    lines.append(f"  TARGET {pid}: not found on any roster")
                    continue
                av = vm.get(pid)
                owner = info.get("owner_team_id", "?")
                lines.append(f"  TARGET (manager asked for): {info['name']} "
                             f"({info['position'].value}) on team {owner}, "
                             f"value {av.value:.0f}" if av else
                             f"  TARGET (manager asked for): {info['name']} on team {owner}")

        for r in self.all_rosters():
            if r.team_id == self.team_id:
                continue
            their_needs = self.roster_needs(r)
            their_chips = self.trade_chips(r)
            # What they could realistically give up at a position I want.
            gettable = [(rp, av) for rp, av in their_chips
                        if rp.player.position in want_positions][:3]
            # Where they are short and my depth is leverage.
            they_need = [p for p in offer_positions
                         if their_needs.get(p, {}).get("need")]
            if not gettable and not they_need:
                continue
            lines.append(f"\n  Team {r.team_id} ({r.owner_name}):")
            for rp, av in gettable:
                slot = "starter" if rp.is_starter else "bench"
                lines.append(f"    could acquire: {rp.player.name} "
                             f"({rp.player.position.value}, {slot}) value {av.value:.0f} "
                             f"[{rp.player.platform_id}]")
            if they_need:
                lines.append(f"    they NEED {[p.value for p in they_need]} — "
                             f"my depth there is leverage")
        if len(lines) <= 2:
            lines.append("  No cross-roster fits found.")
        return "\n".join(lines)

    def _tool_get_trade_value(self, tool_input: dict) -> str:
        ids = tool_input.get("player_ids", [])
        vm = self.value_map()
        idx = self.player_index()
        # value_map is uniform (all market/unranked, or all model) — one entry tells us.
        sample = next(iter(vm.values()), None)
        market = sample is not None and sample.source in ("market", "unranked")
        header = (
            "Trade values (FantasyCalc market consensus for this league format — the "
            "real currency other managers trade in; a value of 0 means waiver/"
            "replacement level with no trade value):"
            if market else
            "Asset values (in-house rest-of-season projection × positional scarcity — "
            "FantasyCalc market values unavailable):"
        )
        lines = [header]
        for pid in ids:
            av = vm.get(pid)
            if av is None:
                lines.append(f"  {pid}: no value (not found / no projection)")
                continue
            prefix = f"  {pid} | {idx.get(pid, {}).get('name', pid)} ({av.position.value}) | "
            if av.source == "market":
                detail = f"value {av.value:.0f} (market {av.note})"
            elif av.source == "unranked":
                detail = "value 0 (waiver/replacement level — no trade value)"
            else:
                detail = (f"RoS={av.ros_points:.1f} × scarcity {av.scarcity:.2f} "
                          f"= value {av.value:.1f}")
            lines.append(prefix + detail)
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
            "Trade evaluation (my perspective):",
            f"  SEND ({names(send_ids)}): value {ev.send_value:.1f}",
            f"  RECEIVE ({names(receive_ids)}): value {ev.receive_value:.1f}",
            f"  EV delta: {ev.ev_delta:+.1f} | fairness {ev.fairness:.2f} | verdict: {ev.verdict.upper()}",
        ]
        if ev.roster_impact:
            lines.append(
                f"  Starting-lineup impact this week: "
                f"{ev.roster_impact.before_total:.1f} → {ev.roster_impact.after_total:.1f} "
                f"({ev.roster_impact.delta:+.1f})")

        # `counterparty_team_id` is optional on the tool and models routinely omit
        # it. The owner of the incoming players is known here, so derive it rather
        # than storing None — a package with no counterparty renders as "team
        # None" in the send-offer steps and cannot be acted on.
        counterparty = tool_input.get("counterparty_team_id")
        if not counterparty:
            owners = {idx[i].get("owner_team_id") for i in receive_ids if i in idx}
            owners.discard(self.team_id)
            owners.discard(None)
            if len(owners) == 1:
                counterparty = next(iter(owners))

        # The same package gets re-priced repeatedly in a long run; scoring is
        # deterministic, so a duplicate adds nothing and would let one trade fill
        # every slot of a deterministic recommendation. Keyed on the players
        # only: `counterparty_team_id` is not an input to the scoring, so
        # including it would let a model re-admit an identical package just by
        # sending (or omitting) a different team id.
        key = (frozenset(send_ids), frozenset(receive_ids))
        if any((frozenset(e.get("send_player_ids", [])),
                frozenset(e.get("receive_player_ids", []))) == key
               for e in self.evaluations):
            return "\n".join(lines)

        self.evaluations.append({
            "send_player_ids": list(send_ids),
            "receive_player_ids": list(receive_ids),
            "send_names": [idx.get(i, {}).get("name", i) for i in send_ids],
            "receive_names": [idx.get(i, {}).get("name", i) for i in receive_ids],
            "counterparty_team_id": counterparty,
            "send_value": ev.send_value,
            "receive_value": ev.receive_value,
            "ev_delta": ev.ev_delta,
            "fairness": ev.fairness,
            "verdict": ev.verdict.upper(),
            "lineup_delta": ev.roster_impact.delta if ev.roster_impact else 0.0,
            "summary": "\n".join(lines),
        })
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

    def _llm_calls_for(self, count: int, batch_size: int) -> int:
        """How many model calls a batch of `count` players will cost."""
        return (count + batch_size - 1) // batch_size if count else 0

    def _tool_get_injury_report(self, tool_input: dict) -> str:
        """Interpret injuries for a batch of players in one sub-agent call.

        ACTIVE players are answered deterministically and never reach the LLM —
        there is no injury picture to interpret.
        """
        from fantasy_gm.agent.subagents.injury import _BATCH_SIZE
        from fantasy_gm.models import PlayerStatus

        pids = tool_input.get("player_ids") or []
        idx = self.player_index()

        lines: list[str] = []
        pending: list[dict] = []
        pending_pids: list[str] = []
        for pid in pids:
            info = idx.get(pid)
            if not info:
                lines.append(f"Player {pid} not found.")
                continue
            player: Player = info["player"]
            if player.status == PlayerStatus.ACTIVE:
                lines.append(f"{player.name}: ACTIVE — no injury concern.")
                continue
            pending.append({"player_name": player.name, "status": player.status.value})
            pending_pids.append(pid)

        if pending:
            cost = self._llm_calls_for(len(pending), _BATCH_SIZE)
            if self.llm_calls + cost > self.llm_budget:
                for p in pending:
                    lines.append(f"{p['player_name']}: {p['status']} — injury "
                                 f"interpretation skipped (LLM call budget reached).")
            else:
                fn = self.injury_fn or _default_injury_fn
                results = fn(pending)
                for _ in range(cost):
                    self.record_llm_call()
                for p in pending:
                    r = results.get(p["player_name"], {})
                    lines.append(
                        f"Injury read for {p['player_name']}: availability_pct="
                        f"{r.get('availability_pct')}, role_change="
                        f"{r.get('role_change_flag')}. {r.get('note', '')}")

        return "\n".join(lines) or "No players requested."

    def _tool_get_player_news(self, tool_input: dict) -> str:
        """Interpret recent news for a batch of players in one sub-agent call."""
        from fantasy_gm.agent.subagents.news import _BATCH_SIZE

        pids = tool_input.get("player_ids") or []
        idx = self.player_index()

        lines: list[str] = []
        names: list[str] = []
        for pid in pids:
            info = idx.get(pid)
            if not info:
                lines.append(f"Player {pid} not found.")
                continue
            names.append(info["name"])

        if names:
            cost = self._llm_calls_for(len(names), _BATCH_SIZE)
            if self.llm_calls + cost > self.llm_budget:
                lines.append("News interpretation skipped for "
                             f"{', '.join(names)} (LLM call budget reached).")
            else:
                fn = self.news_fn or _default_news_fn
                results = fn(names)
                for _ in range(cost):
                    self.record_llm_call()
                for name in names:
                    r = results.get(name, {})
                    head = (f"News read for {name}: net outlook "
                            f"{r.get('net_outlook', 'neutral')}. {r.get('note', '')}")
                    for e in (r.get("events") or [])[:4]:
                        head += f"\n  - [{e.get('type')}/{e.get('impact')}] {e.get('summary')}"
                    lines.append(head)

        return "\n".join(lines) or "No players requested."

    def _tool_propose_trades(self, tool_input: dict) -> str:
        import json
        idx = self.player_index()
        prefs = self.preferences
        constrained = prefs is not None and not prefs.is_empty()
        names = self.name_map() if constrained else {}
        enriched = dict(tool_input)
        for pkg in enriched.get("trades", []):
            send = pkg.get("send_player_ids", [])
            receive = pkg.get("receive_player_ids", [])
            pkg["send_names"] = [idx.get(i, {}).get("name", i) for i in send]
            pkg["receive_names"] = [idx.get(i, {}).get("name", i) for i in receive]
            # Record where a package contradicts the manager's directives. The
            # human still decides — a near-miss is worth seeing, not hiding.
            if constrained:
                problems = prefs.violations(send, receive, names)
                if problems:
                    pkg["directive_violations"] = problems
        return json.dumps(enriched)

    def _tool_abstain(self, tool_input: dict) -> str:
        import json
        return json.dumps(tool_input)


def _default_injury_fn(players: list[dict]) -> dict[str, dict]:
    from fantasy_gm.agent.subagents.injury import interpret_injuries
    return interpret_injuries(players)


def _default_news_fn(player_names: list[str]) -> dict[str, dict]:
    from fantasy_gm.agent.subagents.news import interpret_news_batch
    return interpret_news_batch(player_names)


# ---------------------------------------------------------------------------
# Deterministic package selection
# ---------------------------------------------------------------------------

# A package the other owner would plausibly accept. Below this the deal is a
# fleece and gets declined in real leagues, so it is not a recommendation.
_MIN_FAIRNESS = 0.70
# Require a real gain, not rounding noise, before recommending a trade.
_MIN_EV_DELTA = 50.0


def acceptable_packages(evaluations: list[dict], preferences: Any = None,
                        names: dict[str, str] | None = None) -> list[dict]:
    """Rank the priced packages worth recommending, best first.

    The scoring is already deterministic, so choosing among evaluated packages
    needs no model call. Keeps only deals that gain real value AND are balanced
    enough that the counterparty would plausibly accept, then sorts by gain.

    Packages that contradict the manager's directives are excluded outright —
    unlike the model path, where a violation is surfaced as a warning, nothing
    here can explain itself, so it must not quietly propose something the
    manager ruled out.
    """
    viable = []
    for ev in evaluations:
        if ev.get("fairness", 0.0) < _MIN_FAIRNESS:
            continue
        if ev.get("ev_delta", 0.0) < _MIN_EV_DELTA:
            continue
        if preferences is not None and not preferences.is_empty():
            if preferences.violations(ev.get("send_player_ids", []),
                                      ev.get("receive_player_ids", []),
                                      names or {}):
                continue
        viable.append(ev)
    # Best gain first; break ties on fairness so the easier sell wins.
    return sorted(viable, key=lambda e: (e.get("ev_delta", 0.0),
                                         e.get("fairness", 0.0)), reverse=True)
