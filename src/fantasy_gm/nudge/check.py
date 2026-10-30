"""Pre-kickoff nudge check.

`should_nudge` is the pure decision function — it reads from the store,
applies the threshold, and fires through the notifier. The clock and
kickoff time are injected so tests can control them without patching.

`next_sunday_kickoff_utc` derives the next Sunday 1 PM ET deadline from
a given reference time. Used by the launchd script and the web endpoint.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fantasy_gm.db.store import DecisionStore
from fantasy_gm.models import DecisionType
from fantasy_gm.nudge.notify import MacNotifier, NudgeDeliveryFailed

_ET = ZoneInfo("America/New_York")
_DEFAULT_THRESHOLD = 120  # minutes


def should_nudge(
    store: DecisionStore,
    week: int,
    season: int,
    kickoff_utc: datetime,
    notifier: MacNotifier | None = None,
    now_utc: datetime | None = None,
    threshold_minutes: int = _DEFAULT_THRESHOLD,
) -> bool:
    """Return True if a nudge was successfully delivered, False otherwise.

    Never raises — delivery failures are logged to nudge_log.
    """
    if threshold_minutes <= 0:
        return False

    now = now_utc or datetime.utcnow()

    if now >= kickoff_utc:
        return False

    minutes_remaining = (kickoff_utc - now).total_seconds() / 60
    if minutes_remaining > threshold_minutes:
        return False

    decisions = store.list_week(week, season)
    lineup = next(
        (d for d in decisions if d.decision_type == DecisionType.LINEUP),
        None,
    )
    if lineup is None:
        return False

    if lineup.human_response is not None:
        return False

    notifier = notifier or MacNotifier()
    try:
        notifier.notify(minutes_remaining)
        return True
    except NudgeDeliveryFailed as exc:
        store.log_nudge_failure(week, season, str(exc))
        return False


def next_sunday_kickoff_utc(ref: datetime | None = None) -> datetime:
    """Return the next Sunday 1 PM ET as a UTC datetime."""
    now_et = (ref or datetime.utcnow()).replace(tzinfo=ZoneInfo("UTC")).astimezone(_ET)
    days_until_sunday = (6 - now_et.weekday()) % 7
    if days_until_sunday == 0 and now_et.hour >= 13:
        days_until_sunday = 7
    sunday_et = now_et.replace(hour=13, minute=0, second=0, microsecond=0) + timedelta(days=days_until_sunday)
    return sunday_et.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def run_check(
    db_path: Path,
    week: int,
    season: int,
    kickoff_utc: datetime | None = None,
    threshold_minutes: int = _DEFAULT_THRESHOLD,
) -> bool:
    """Entry point for the launchd check script."""
    store = DecisionStore(db_path)
    kickoff = kickoff_utc or next_sunday_kickoff_utc()
    return should_nudge(store, week, season, kickoff, threshold_minutes=threshold_minutes)
