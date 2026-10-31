"""
ESPN waiver executor — files an approved waiver claim through the write endpoint.

A claim is one `WAIVER` transaction carrying an ADD and a DROP item, exactly as
ESPN's own app files it in this league (seen in mTransactions2), so the pair
cannot half-succeed. A filed claim reads back as `PENDING` until the window
processes it; whether it then cleared or lost to priority is read later.

FRAGILE: the endpoint is undocumented. Dry-run by default; only POSTs on
live=True, which only the shared approval gate (`execute/gate.py`) produces.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

from fantasy_gm.execute.trade_api import ESPN_WRITE_URL


@dataclass
class WaiverClaimPlan:
    add_id: str
    add_name: str
    drop_id: str
    drop_name: str
    team_id: str
    week: int
    season: int
    request_payload: dict
    human_steps: list[str] = field(default_factory=list)


@dataclass
class WaiverFilingResult:
    success: bool
    dry_run: bool
    plan: WaiverClaimPlan
    message: str = ""
    error: str | None = None
    confirmed: bool | None = None
    """Three states, as with the trade send:
      True   — ESPN accepted it and it reads back as a pending claim.
      False  — ESPN accepted it but the read-back cannot find it. Never re-file
               on this; a duplicate claim is worse than an unverified one.
      None   — nothing live was attempted, or the send itself failed.
    """


def build_espn_waiver_claim(team_id: str, add_id: str, drop_id: str,
                            week: int, season: int, swid: str) -> dict:
    """The ESPN `WAIVER` transaction body: one ADD from the pool, one DROP to it."""
    mine = int(team_id)
    return {
        "isLeagueManager": False,
        "teamId": mine,
        "type": "WAIVER",
        "memberId": swid,
        "scoringPeriodId": week,
        "executionType": "EXECUTE",
        "bidAmount": 0,
        "items": [
            {"playerId": int(add_id), "type": "ADD", "fromTeamId": 0, "toTeamId": mine},
            {"playerId": int(drop_id), "type": "DROP", "fromTeamId": mine, "toTeamId": 0},
        ],
    }


class ESPNWaiverApiExecutor:
    """Files a waiver claim through ESPN's write API. Dry-run unless live=True."""

    name = "espn-waiver-api"

    def __init__(self, adapter):
        self.adapter = adapter
        self._swid = os.environ.get("ESPN_SWID", "")
        self._espn_s2 = os.environ.get("ESPN_S2", "")

    def plan(self, add_id: str, add_name: str, drop_id: str, drop_name: str,
             team_id: str, week: int, season: int) -> WaiverClaimPlan:
        return WaiverClaimPlan(
            add_id=str(add_id), add_name=add_name, drop_id=str(drop_id), drop_name=drop_name,
            team_id=str(team_id), week=week, season=season,
            request_payload=build_espn_waiver_claim(team_id, add_id, drop_id, week, season,
                                                    self._swid),
            human_steps=[f"Add {add_name}", f"Drop {drop_name}"],
        )

    def check_still_legal(self, plan: WaiverClaimPlan) -> str | None:
        """Re-read the league; return why the pair is no longer legal, or None (I-12)."""
        roster = self.adapter.get_roster(plan.team_id, plan.week, plan.season, fresh=True)
        if plan.drop_id not in {rp.player.platform_id for rp in roster.players}:
            return f"Nothing was sent — {plan.drop_name} is no longer on your roster."
        pool = self.adapter.get_free_agents(plan.week, plan.season, fresh=True)
        if plan.add_id not in {fa.player.platform_id for fa in pool}:
            return f"Nothing was sent — {plan.add_name} is no longer available."
        return None

    def execute(self, plan: WaiverClaimPlan, live: bool = False) -> WaiverFilingResult:
        if not live:
            return WaiverFilingResult(
                True, dry_run=True, plan=plan,
                message=f"Dry run — nothing was sent. Add {plan.add_name} · Drop "
                        f"{plan.drop_name} · waiver claim for week {plan.week}.",
            )
        if not (self._swid and self._espn_s2):
            return WaiverFilingResult(False, dry_run=False, plan=plan,
                                      error="ESPN credentials (ESPN_SWID / ESPN_S2) are not set, "
                                            "so nothing was sent")
        try:
            resp = httpx.post(
                ESPN_WRITE_URL.format(season=plan.season, league_id=self.adapter.league_id),
                json=plan.request_payload,
                cookies={"SWID": self._swid, "espn_s2": self._espn_s2},
                headers={
                    "Content-Type": "application/json",
                    "X-Fantasy-Platform": "kona-PROD",
                    "X-Fantasy-Source": "kona",
                },
                timeout=20,
            )
            if resp.status_code >= 400:
                body = resp.text[:500] if resp.text else "(empty body)"
                return WaiverFilingResult(False, dry_run=False, plan=plan,
                                          error=f"ESPN API {resp.status_code}: {body}")
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            # The connection never opened, so ESPN cannot have the claim.
            return WaiverFilingResult(False, dry_run=False, plan=plan,
                                      error=f"could not reach ESPN: {e}")
        except Exception:
            # Anything later — a read timeout, a dropped response — may have
            # reached ESPN. Never call that "not filed": let the read-back decide.
            pass

        if self._confirm_filed(plan):
            return WaiverFilingResult(True, dry_run=False, plan=plan, confirmed=True,
                                      message="Claim filed — ESPN shows it as pending.")
        return WaiverFilingResult(
            True, dry_run=False, plan=plan, confirmed=False,
            message="ESPN accepted the claim but it doesn't show on the league yet. "
                    "Check the ESPN app before doing anything — don't file again, "
                    "or you may end up with two claims.",
        )

    def _confirm_filed(self, plan: WaiverClaimPlan) -> bool:
        """Find this claim among the league's pending waiver transactions (I-23).

        Matches on my team, this week, and the exact add and drop, so an older
        pending claim of mine does not count. A failed read is unconfirmed,
        never assumed good.
        """
        try:
            pending = self.adapter.get_pending_waiver_claims(plan.season)
        except Exception:
            return False
        want = {("ADD", plan.add_id), ("DROP", plan.drop_id)}
        for txn in pending:
            if str(txn.get("teamId")) != plan.team_id:
                continue
            if txn.get("scoringPeriodId") not in (None, plan.week):
                continue
            got = {(str(i.get("type")), str(i.get("playerId"))) for i in txn.get("items", [])}
            if got == want:
                return True
        return False
