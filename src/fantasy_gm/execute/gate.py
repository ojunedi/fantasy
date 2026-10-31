"""The approval gate: the one rule that decides whether a write goes to ESPN.

Every surface that can write — the command line's lineup write and trade send,
the web app's lineup write — asks this, and nothing else compares a
confirmation against `LIVE`.

  - The decision must be approved or overridden (I-11); an override must carry
    a written reason (I-09). Otherwise the execution is refused outright — not
    even a dry run, so nothing invites the next attempt to be live.
  - The confirmation must be exactly `LIVE`: case-sensitive, untrimmed (I-24).
    Anything else is a dry run.

Pure: it reads the decision it is handed and stores nothing, so every
execution is authorised afresh (I-24). Callers hand it the decision as the
decision log holds it, never anything a client sent.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from fantasy_gm.models import DecisionRecord, HumanResponse

_STATE_NAMES = {
    None: "pending",
    HumanResponse.REJECTED: "rejected",
    HumanResponse.DECLINED: "declined",
}


class Verdict(str, Enum):
    LIVE = "live"
    DRY_RUN = "dry_run"
    REFUSED = "refused"


@dataclass(frozen=True)
class Authorisation:
    verdict: Verdict
    code: str | None = None
    message: str = ""

    @property
    def live(self) -> bool:
        return self.verdict is Verdict.LIVE

    @property
    def refused(self) -> bool:
        return self.verdict is Verdict.REFUSED


def authorise(record: DecisionRecord, confirmation: str | None) -> Authorisation:
    """Decide this one execution of `record`: live, dry run, or refused."""
    response = record.human_response
    if response not in (HumanResponse.APPROVED, HumanResponse.MODIFIED):
        state = _STATE_NAMES.get(response, getattr(response, "value", str(response)))
        return Authorisation(
            Verdict.REFUSED, "NOT_APPROVED",
            f"This decision is {state}, not approved — nothing was sent.",
        )
    if response is HumanResponse.MODIFIED and not (record.override_reason or "").strip():
        return Authorisation(
            Verdict.REFUSED, "OVERRIDE_REASON_MISSING",
            "This override has no written reason — nothing was sent.",
        )
    if confirmation == "LIVE":  # the only LIVE comparison in the source
        return Authorisation(Verdict.LIVE)
    return Authorisation(Verdict.DRY_RUN)
