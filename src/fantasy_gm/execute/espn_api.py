"""
ESPN API executor — sets the lineup via ESPN's reverse-engineered write endpoint.

FRAGILE: this endpoint is undocumented and may break on ESPN changes. It is
dry-run by default and only POSTs when live=True. On any failure the caller
(FallbackExecutor) can fall back to the browser executor.
"""
from __future__ import annotations

import os

import httpx

from fantasy_gm.adapters.espn import ESPNAdapter
from fantasy_gm.execute.base import Executor, ExecutionPlan, ExecutionResult
from fantasy_gm.execute.lineup_plan import (
    build_espn_transaction,
    build_target_slots,
    plan_moves,
    slot_name,
)

ESPN_WRITE_URL = (
    "https://lm-api-writes.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}"
    "/segments/0/leagues/{league_id}/transactions/"
)


class ESPNApiExecutor(Executor):
    name = "espn_api"

    def __init__(self, adapter: ESPNAdapter):
        self.adapter = adapter
        self._swid = os.environ.get("ESPN_SWID", "")
        self._espn_s2 = os.environ.get("ESPN_S2", "")

    def plan_set_lineup(
        self, team_id: str, week: int, season: int, starter_player_ids: list[str]
    ) -> ExecutionPlan:
        roster = self.adapter.get_roster(team_id, week, season)
        current = self.adapter.get_raw_lineup_slots(team_id, week, season)
        names = {rp.player.platform_id: rp.player.name for rp in roster.players}
        settings = self.adapter.get_league_settings(season)

        target = build_target_slots(roster.players, starter_player_ids, settings)
        moves = plan_moves(current, target, names)
        payload = build_espn_transaction(team_id, week, season, moves, self._swid) if moves else None

        plan = ExecutionPlan(
            action_type="set_lineup",
            moves=moves,
            request_payload=payload,
            human_steps=[m.describe(slot_name) for m in moves],
            context={"season": season, "week": week, "team_id": team_id},
        )
        if not moves:
            plan.notes.append("Proposed lineup already matches current lineup — nothing to do.")
        if not (self._swid and self._espn_s2):
            plan.notes.append("WARNING: ESPN_SWID / ESPN_S2 not set — live execution would fail auth.")
        return plan

    def execute(self, plan: ExecutionPlan, live: bool = False) -> ExecutionResult:
        if plan.is_noop:
            return ExecutionResult(True, dry_run=not live, executor=self.name, plan=plan,
                                   message="No moves needed.")
        if not live:
            return ExecutionResult(
                True, dry_run=True, executor=self.name, plan=plan,
                message=f"DRY RUN: would POST {len(plan.moves)} lineup move(s) to ESPN.",
            )
        if not (self._swid and self._espn_s2):
            return ExecutionResult(False, dry_run=False, executor=self.name, plan=plan,
                                   error="ESPN_SWID/ESPN_S2 not set; cannot authenticate write.")
        try:
            url = ESPN_WRITE_URL.format(season=plan.context["season"],
                                        league_id=self.adapter.league_id)
            resp = httpx.post(
                url,
                json=plan.request_payload,
                cookies={"SWID": self._swid, "espn_s2": self._espn_s2},
                headers={
                    "Content-Type": "application/json",
                    "X-Fantasy-Platform": "kona-PROD",
                    "X-Fantasy-Source": "kona",
                },
                timeout=20,
            )
            if resp.status_code == 409:
                try:
                    body = resp.json()
                except Exception:
                    body = {}
                details = body.get("details", [])
                same_slot_types = {"TRAN_ROSTER_SAME_SLOT"}
                all_same_slot = details and all(
                    d.get("type") in same_slot_types for d in details
                )
                if all_same_slot:
                    return ExecutionResult(
                        True, dry_run=False, executor=self.name, plan=plan,
                        message="Lineup already matches ESPN — no moves needed.",
                    )
                # Partial same-slot: drop the already-correct moves and retry.
                same_slot_msgs = {
                    d.get("message", "") for d in details
                    if d.get("type") in same_slot_types
                }
                if same_slot_msgs:
                    filtered = [
                        m for m in plan.moves
                        if not any(m.player_name in msg for msg in same_slot_msgs)
                    ]
                    if filtered and filtered != plan.moves:
                        plan.moves = filtered
                        plan.request_payload = build_espn_transaction(
                            plan.context["team_id"], plan.context["week"],
                            plan.context["season"], filtered, self._swid,
                        )
                        return self.execute(plan, live=live)
                body_text = resp.text[:2000] if resp.text else "(empty)"
                return ExecutionResult(
                    False, dry_run=False, executor=self.name, plan=plan,
                    error=f"ESPN API 409: {body_text}",
                )
            if resp.status_code >= 400:
                body = resp.text[:2000] if resp.text else "(empty body)"
                return ExecutionResult(
                    False, dry_run=False, executor=self.name, plan=plan,
                    error=f"ESPN API {resp.status_code}: {body}",
                )
            return ExecutionResult(True, dry_run=False, executor=self.name, plan=plan,
                                   message=f"Executed {len(plan.moves)} move(s) via ESPN API.")
        except Exception as e:
            return ExecutionResult(False, dry_run=False, executor=self.name, plan=plan,
                                   error=f"ESPN API write failed: {e}")
