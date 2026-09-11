"""
Playwright browser executor — sets the lineup by driving the real ESPN UI.

Robust to ESPN API changes (it uses the same UI a human would) and the only
viable write path for Sleeper. Heavier: requires `playwright` + a browser binary
(`uv run playwright install chromium`). Lazily imported so the rest of the app
works without it.

Dry-run by default. The reuse of the deterministic planner means this executor
carries out the same validated moves as the API executor.
"""
from __future__ import annotations

import os

from fantasy_gm.adapters.espn import ESPNAdapter
from fantasy_gm.execute.base import Executor, ExecutionPlan, ExecutionResult
from fantasy_gm.execute.lineup_plan import (
    build_target_slots,
    plan_moves,
    slot_name,
)


def playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


class PlaywrightExecutor(Executor):
    name = "playwright"

    def __init__(self, adapter: ESPNAdapter, headless: bool = True):
        self.adapter = adapter
        self.headless = headless
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

        plan = ExecutionPlan(
            action_type="set_lineup",
            moves=moves,
            human_steps=[m.describe(slot_name) for m in moves],
        )
        plan.notes.append(
            f"Browser plan: navigate to team {team_id} lineup for week {week} and apply "
            f"{len(moves)} move(s)."
        )
        if not playwright_available():
            plan.notes.append("Playwright not installed — run `uv run playwright install chromium`.")
        return plan

    def execute(self, plan: ExecutionPlan, live: bool = False) -> ExecutionResult:
        if plan.is_noop:
            return ExecutionResult(True, dry_run=not live, executor=self.name, plan=plan,
                                   message="No moves needed.")
        if not live:
            return ExecutionResult(
                True, dry_run=True, executor=self.name, plan=plan,
                message=f"DRY RUN: would drive the ESPN UI to apply {len(plan.moves)} move(s).",
            )
        if not playwright_available():
            return ExecutionResult(
                False, dry_run=False, executor=self.name, plan=plan,
                error="Playwright not installed. Run `uv run playwright install chromium`.",
            )
        if not (self._swid and self._espn_s2):
            return ExecutionResult(False, dry_run=False, executor=self.name, plan=plan,
                                   error="ESPN_SWID/ESPN_S2 not set; cannot authenticate the session.")
        try:
            self._drive_browser(plan)
            return ExecutionResult(True, dry_run=False, executor=self.name, plan=plan,
                                   message=f"Applied {len(plan.moves)} move(s) via browser.")
        except Exception as e:
            return ExecutionResult(False, dry_run=False, executor=self.name, plan=plan,
                                   error=f"Browser automation failed: {e}")

    def _drive_browser(self, plan: ExecutionPlan) -> None:
        """Drive the ESPN lineup UI. Implemented against the real site; the exact
        selectors are validated during the season (ESPN's DOM changes across
        seasons). Kept isolated so selector maintenance touches only this method."""
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context()
            context.add_cookies([
                {"name": "SWID", "value": self._swid, "domain": ".espn.com", "path": "/"},
                {"name": "espn_s2", "value": self._espn_s2, "domain": ".espn.com", "path": "/"},
            ])
            page = context.new_page()
            # NOTE: navigation + per-move drag/drop selectors are finalized against
            # the live site during the season; raising keeps live=True honest until then.
            raise NotImplementedError(
                "Browser selectors are validated live during the season; use the ESPN "
                "API executor for now, or run in dry-run mode."
            )
