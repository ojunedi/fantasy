"""Missed lineup recommendations, and what they cost.

A week is missed when none of its lineup decisions was approved or overridden
by kickoff. The miss is written to the newest unactioned decision's outcome —
never as a human response or an override reason, because silence is not a
choice and must not read as one in the override log (I-09).

The cost is measured with the projections saved on the decision when it was
made, which predate kickoff (I-14): recommended starters' projected total
minus the standing starters'. Actual points are recorded beside it as labelled
hindsight and are never the cost.

`python -m fantasy_gm.nudge.missed` runs it by hand; the history page runs it
on every load.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fantasy_gm.db.store import DecisionStore
from fantasy_gm.models import DecisionRecord, DecisionType


_ET = ZoneInfo("America/New_York")


def week_kickoff(season: int, week: int) -> datetime:
    """Sunday 1 PM ET of NFL week `week`, as naive UTC.

    Week 1's Sunday is the Sunday after Labor Day (the first Monday of
    September); each later week is seven days on. Derived from the week number,
    never from when a decision was made: a run made on Monday belongs to the
    week that just kicked off, not to the next one.
    """
    labor_day = date(season, 9, 1)
    labor_day += timedelta(days=(0 - labor_day.weekday()) % 7)
    sunday = labor_day + timedelta(days=6 + 7 * (week - 1))
    kickoff = datetime(sunday.year, sunday.month, sunday.day, 13, tzinfo=_ET)
    return kickoff.astimezone(timezone.utc).replace(tzinfo=None)


def week_settled(season: int, week: int) -> datetime:
    """Tuesday 6 AM ET after the week's Sunday — every game, Monday night's
    included, is final, and nothing in the lineup can still move."""
    sunday_et = week_kickoff(season, week).replace(tzinfo=timezone.utc).astimezone(_ET)
    tuesday = (sunday_et + timedelta(days=2)).replace(hour=6, minute=0)
    return tuesday.astimezone(timezone.utc).replace(tzinfo=None)


def _naive_utc(moment: datetime) -> datetime:
    if moment.tzinfo is not None:
        return moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment


def missed_cost(record: DecisionRecord, standing_ids: list[str],
                actual: dict[str, float] | None) -> dict:
    """The miss as recorded: cost from saved projections, actuals as hindsight."""
    projections = (record.inputs_snapshot or {}).get("projections") or {}
    recommended = [str(p) for p in (record.recommendation or {}).get("starter_player_ids") or []]
    standing = [str(p) for p in standing_ids]

    recommended_projected = round(sum(projections.get(p, 0.0) for p in recommended), 2)
    standing_projected = round(sum(projections.get(p, 0.0) for p in standing), 2)
    # Either side's missing number moves the cost, so both are named.
    unprojected = [p for p in dict.fromkeys(recommended + standing) if p not in projections]

    hindsight = None
    if actual:
        hindsight = {
            "recommended_actual": round(sum(actual.get(p, 0.0) for p in recommended), 2),
            "standing_actual": round(sum(actual.get(p, 0.0) for p in standing), 2),
        }
    return {
        "cost": round(recommended_projected - standing_projected, 2),
        "recommended_ids": recommended,
        "standing_ids": standing,
        "recommended_projected": recommended_projected,
        "standing_projected": standing_projected,
        "unprojected": unprojected,
        "kickoff": week_kickoff(record.season, record.week).isoformat(),
        "hindsight": hindsight,
    }


def record_missed_lineups(store: DecisionStore, adapter, team_id: str, season: int,
                          now: datetime | None = None) -> list[str]:
    """Record every settled, missed week this season not yet recorded.

    A week is missed when none of its lineup runs made before kickoff got a
    response before kickoff. It is recorded only once the week is settled
    (Tuesday morning), against a fresh read of the lineup that played, so the
    cost cannot depend on when this happened to run. One week or record
    failing never stops the others; it is tried again next time.
    """
    now = _naive_utc(now or datetime.utcnow())
    weeks: dict[int, list[DecisionRecord]] = {}
    for r in store.list_recent(limit=5000):
        if r.decision_type == DecisionType.LINEUP and r.season == season:
            weeks.setdefault(r.week, []).append(r)

    recorded = []
    for week, records in sorted(weeks.items()):
        try:
            kickoff = week_kickoff(season, week)
            if now < week_settled(season, week):
                continue
            if any((r.outcome or {}).get("missed") for r in records):
                continue  # recorded once, never recomputed

            def acted_before_kickoff(r: DecisionRecord) -> bool:
                if r.human_response is None:
                    return False
                # A response logged before response times were kept is
                # taken as in time — the log cannot say otherwise.
                return r.responded_at is None or _naive_utc(r.responded_at) < kickoff

            if any(acted_before_kickoff(r) for r in records):
                continue
            # Only a run that recommended starters, made before kickoff, could
            # have been acted on; an abstention or a post-kickoff run could not.
            candidates = [r for r in records
                          if (r.recommendation or {}).get("starter_player_ids")
                          and _naive_utc(r.created_at) < kickoff]
            if not candidates:
                continue
            newest = max(candidates, key=lambda r: _naive_utc(r.created_at))

            try:
                roster = adapter.get_roster(team_id, week, season, fresh=True)
                standing = [rp.player.platform_id for rp in roster.players if rp.is_starter]
            except Exception:
                continue
            try:
                actual = adapter.get_actual_scores(week, season)
            except Exception:
                actual = None
            store.record_outcome(newest.id, {**(newest.outcome or {}),
                                             "missed": missed_cost(newest, standing, actual)})
            recorded.append(str(newest.id))
        except Exception as exc:  # a malformed record must not hide every other week
            print(f"missed-week check skipped week {week}: {type(exc).__name__}: {exc}",
                  file=sys.stderr)
    return recorded


def main() -> None:
    from fantasy_gm.web.settings import WebSettings
    from fantasy_gm.web.deps import build_adapter

    settings = WebSettings()
    store = DecisionStore(settings.db_path)
    ids = record_missed_lineups(store, build_adapter(settings), settings.team_id, settings.season)
    store.backup_if_dirty()
    print(f"{len(ids)} missed week(s) recorded")


if __name__ == "__main__":
    sys.exit(main())
