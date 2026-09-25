"""
Trade "execution" — propose-only.

An ESPN trade cannot be executed unilaterally: the counterparty has to accept
the offer in-app. So there is no live write path here. This executor turns an
approved trade package into the exact steps to send the offer in the ESPN app,
mirroring the dry-run-by-default contract of the lineup `Executor` without
pretending it can write.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TradeSendPlan:
    counterparty_team_id: str
    send_names: list[str]
    receive_names: list[str]
    human_steps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # Set only by the API executor; the manual renderer leaves it None.
    request_payload: dict[str, Any] | None = None


class TradeProposalExecutor:
    """Renders the manual steps to send a trade offer. Never writes."""

    name = "espn-trade-manual"

    def plan(self, trade: dict) -> TradeSendPlan:
        send = trade.get("send_names") or trade.get("send_player_ids", [])
        receive = trade.get("receive_names") or trade.get("receive_player_ids", [])
        counterparty = str(trade.get("counterparty_team_id", "?"))
        steps = [
            "Open the ESPN Fantasy app → your league → the LM/Team menu → 'Trade'.",
            f"Select the trade partner: team {counterparty}.",
            f"Offer to send: {', '.join(map(str, send)) or '(none)'}.",
            f"Request to receive: {', '.join(map(str, receive)) or '(none)'}.",
            "Paste the pitch below into the trade note, then send.",
        ]
        notes = []
        if trade.get("counterparty_pitch"):
            notes.append(f"Pitch: {trade['counterparty_pitch']}")
        if trade.get("rationale"):
            notes.append(f"Why it helps me: {trade['rationale']}")
        return TradeSendPlan(
            counterparty_team_id=counterparty, send_names=list(map(str, send)),
            receive_names=list(map(str, receive)), human_steps=steps, notes=notes,
        )
