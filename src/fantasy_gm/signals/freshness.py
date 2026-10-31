"""How old is too old: per-signal thresholds for a lineup decision.

The bundle is fresh only when every signal the decision depends on is
available, stamped and within its threshold (I-02). Missing or unstamped is
stale, never fresh (I-01). Optional enrichments that go stale are named, but
cannot stop a lineup that does not need them.

Thresholds (hotspot H-02), and what can actually trip them:
  - projections: the ESPN disk cache refetches after an hour and a failed
    refetch raises, so in practice this trips as *missing* — the Sunday-outage
    case. The 6h age guards a future source that can serve old data.
  - injuries: read live with the roster each run; the hour is a backstop.
  - usage trends, Vegas lines: stamped with their nflverse file's real age,
    because a failed reload quietly serves the old copy — these do trip.
  - weather: fetched live each run.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from fantasy_gm.signals.base import SignalBundle

HOUR = 3600
THRESHOLDS: dict[str, float] = {
    "projections": 6 * HOUR,
    "injuries": 1 * HOUR,
    "usage_trends": 7 * 24 * HOUR,
    "vegas_lines": 24 * HOUR,
    "weather": 12 * HOUR,
    # Stamped with the feed's scrape *date* (midnight), so a day's slack is built in.
    "expert_rankings": 48 * HOUR,
}
REQUIRED = frozenset({"projections", "injuries"})


@dataclass
class Freshness:
    fresh: bool
    stale: list[dict] = field(default_factory=list)   # every failing signal, required or not

    @property
    def blocking(self) -> list[dict]:
        return [s for s in self.stale if s["required"]]


def _describe(threshold: float) -> str:
    return f"{threshold / 86400:g} days" if threshold >= 86400 else f"{threshold / HOUR:g}h"


def assess(bundle: SignalBundle, now: datetime | None = None) -> Freshness:
    now = now or datetime.utcnow()
    seen = {a.name: a for a in bundle.availability}
    stale = []
    for name, threshold in THRESHOLDS.items():
        a = seen.get(name)
        required = name in REQUIRED
        if a is None or not a.available:
            reason = "missing" if a is None else f"missing ({a.note})" if a.note else "missing"
            stale.append({"name": name, "required": required, "age_seconds": None,
                          "threshold_seconds": threshold, "reason": reason})
            continue
        if a.as_of is None:
            stale.append({"name": name, "required": required, "age_seconds": None,
                          "threshold_seconds": threshold, "reason": "no as-of time"})
            continue
        age = (now - a.as_of).total_seconds()
        if age > threshold:
            stale.append({"name": name, "required": required, "age_seconds": round(age),
                          "threshold_seconds": threshold,
                          "reason": f"{timedelta(seconds=round(age))} old"})
    return Freshness(fresh=not any(s["required"] for s in stale), stale=stale)


def evidence_line(s: dict) -> str:
    return f"{s['name']}: {s['reason']} (threshold {_describe(s['threshold_seconds'])})"
