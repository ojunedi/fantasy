"""
ESPN trade executor — sends a trade OFFER via the reverse-engineered write endpoint.

Sending an offer is one-sided and reversible: it lands in the counterparty's
inbox as a pending proposal and only moves players if they accept. That is what
makes this safe to write, unlike an executed trade.

FRAGILE: the endpoint is undocumented. Dry-run by default; only POSTs on live=True.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from fantasy_gm.adapters.espn import ESPNAdapter
from fantasy_gm.execute.trade_plan import TradeSendPlan

ESPN_WRITE_URL = (
    "https://lm-api-writes.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}"
    "/segments/0/leagues/{league_id}/transactions/"
)


@dataclass
class TradeExecutionResult:
    success: bool
    dry_run: bool
    executor: str
    plan: TradeSendPlan
    message: str = ""
    error: str | None = None


def build_espn_trade_transaction(
    team_id: str,
    counterparty_team_id: str,
    send_player_ids: list[str],
    receive_player_ids: list[str],
    week: int,
    season: int,
    swid: str,
) -> dict:
    """Build the ESPN 'TRADE_PROPOSAL' transaction body.

    Each player is one item. Players leaving my roster go from me to them;
    players I want flip the direction. Trade items carry no lineup slot.
    """
    mine, theirs = int(team_id), int(counterparty_team_id)
    items = [
        {"playerId": int(pid), "type": "TRADE", "fromTeamId": mine, "toTeamId": theirs}
        for pid in send_player_ids
    ] + [
        {"playerId": int(pid), "type": "TRADE", "fromTeamId": theirs, "toTeamId": mine}
        for pid in receive_player_ids
    ]
    return {
        "isLeagueManager": False,
        "teamId": mine,
        "type": "TRADE_PROPOSAL",
        "memberId": swid,
        "scoringPeriodId": week,
        "executionType": "EXECUTE",
        "items": items,
    }


class ESPNTradeApiExecutor:
    """Sends a trade offer through ESPN's write API. Dry-run unless live=True."""

    name = "espn-trade-api"

    def __init__(self, adapter: ESPNAdapter):
        self.adapter = adapter
        self._swid = os.environ.get("ESPN_SWID", "")
        self._espn_s2 = os.environ.get("ESPN_S2", "")

    def plan(self, trade: dict, team_id: str, week: int, season: int) -> TradeSendPlan:
        send_ids = [str(p) for p in trade.get("send_player_ids", [])]
        receive_ids = [str(p) for p in trade.get("receive_player_ids", [])]
        send_names = [str(n) for n in (trade.get("send_names") or send_ids)]
        receive_names = [str(n) for n in (trade.get("receive_names") or receive_ids)]
        counterparty = trade.get("counterparty_team_id")

        notes: list[str] = []
        payload = None

        if counterparty in (None, "", "?"):
            notes.append("BLOCKED: no counterparty_team_id on this package — cannot send.")
        elif not send_ids and not receive_ids:
            notes.append("BLOCKED: package has no players on either side.")
        else:
            payload = build_espn_trade_transaction(
                team_id, str(counterparty), send_ids, receive_ids, week, season, self._swid,
            )

        steps = [
            f"Offer team {counterparty}: send {', '.join(send_names) or '(none)'}",
            f"  in exchange for {', '.join(receive_names) or '(none)'}.",
        ]
        if trade.get("counterparty_pitch"):
            notes.append(f"Pitch (paste in-app — ESPN's API carries no note field): "
                         f"{trade['counterparty_pitch']}")
        if trade.get("rationale"):
            notes.append(f"Why it helps me: {trade['rationale']}")
        if not (self._swid and self._espn_s2):
            notes.append("WARNING: ESPN_SWID / ESPN_S2 not set — live send would fail auth.")

        return TradeSendPlan(
            counterparty_team_id=str(counterparty),
            send_names=send_names,
            receive_names=receive_names,
            human_steps=steps,
            notes=notes,
            request_payload=payload,
        )

    def execute(self, plan: TradeSendPlan, season: int, live: bool = False) -> TradeExecutionResult:
        if plan.request_payload is None:
            return TradeExecutionResult(
                False, dry_run=not live, executor=self.name, plan=plan,
                error="No sendable payload — see plan notes.",
            )
        if not live:
            return TradeExecutionResult(
                True, dry_run=True, executor=self.name, plan=plan,
                message=f"DRY RUN: would offer team {plan.counterparty_team_id} "
                        f"{len(plan.send_names)} for {len(plan.receive_names)}.",
            )
        if not (self._swid and self._espn_s2):
            return TradeExecutionResult(
                False, dry_run=False, executor=self.name, plan=plan,
                error="ESPN_SWID/ESPN_S2 not set; cannot authenticate write.",
            )
        try:
            resp = httpx.post(
                ESPN_WRITE_URL.format(season=season, league_id=self.adapter.league_id),
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
                body = resp.text[:2000] if resp.text else "(empty body)"
                return TradeExecutionResult(
                    False, dry_run=False, executor=self.name, plan=plan,
                    error=f"ESPN API {resp.status_code}: {body}",
                )
            return TradeExecutionResult(
                True, dry_run=False, executor=self.name, plan=plan,
                message=f"Offer sent to team {plan.counterparty_team_id} — "
                        f"pending their acceptance.",
            )
        except Exception as e:
            return TradeExecutionResult(
                False, dry_run=False, executor=self.name, plan=plan,
                error=f"ESPN trade write failed: {e}",
            )
