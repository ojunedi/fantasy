"""
Fallback executor — try the ESPN API writer, fall back to the browser on failure.

Planning uses the API executor (both share the same deterministic planner, so the
plan is identical). On a failed live write, it retries via the browser executor.
Dry-run never falls back — a dry run can't "fail" in a way the browser would fix.
"""
from __future__ import annotations

from fantasy_gm.adapters.espn import ESPNAdapter
from fantasy_gm.execute.base import Executor, ExecutionPlan, ExecutionResult
from fantasy_gm.execute.browser import PlaywrightExecutor
from fantasy_gm.execute.espn_api import ESPNApiExecutor


class FallbackExecutor(Executor):
    name = "espn_api+browser"

    def __init__(self, adapter: ESPNAdapter):
        self.api = ESPNApiExecutor(adapter)
        self.browser = PlaywrightExecutor(adapter)

    def plan_set_lineup(
        self, team_id: str, week: int, season: int, starter_player_ids: list[str]
    ) -> ExecutionPlan:
        return self.api.plan_set_lineup(team_id, week, season, starter_player_ids)

    def execute(self, plan: ExecutionPlan, live: bool = False) -> ExecutionResult:
        result = self.api.execute(plan, live=live)
        if result.success or not live:
            return result
        # Live API write failed — try the browser.
        result.plan.notes.append(f"ESPN API failed ({result.error}); falling back to browser.")
        browser_result = self.browser.execute(plan, live=live)
        browser_result.plan.notes.append("(via fallback after ESPN API failure)")
        return browser_result
