"""When a live lineup write fails on every path: check, then tell the manager.

A failed response is not proof the lineup did not change, so the lineup is
read back first (I-16): if every planned move is already in place, nobody is
told — a false alarm teaches the manager to ignore the next one. Otherwise,
before kickoff, the manager gets a notification through the nudge's channel
with the moves from the plan that was sent (I-11) and the time left. After
kickoff it is only recorded. Nothing here ever raises.

"Every path" is every path that can write: today the ESPN API alone — the
browser fallback refuses live writes until it is built out.
"""
from __future__ import annotations

import sys
from datetime import datetime

from fantasy_gm.nudge.notify import format_minutes


def _step_for(plan, move) -> str:
    """The plan's own words for a move; the step list can lag the moves after a
    partial retry, so it is matched by player rather than by position."""
    return next((s for s in plan.human_steps if s.startswith(f"{move.player_name}:")),
                f"{move.player_name}: to lineup slot {move.to_slot}")


def report_failed_write(store, record, plan, result, adapter, team_id: str,
                        notifier, now: datetime | None = None) -> str:
    """Handle one execution's result. Returns none / landed / notified / recorded."""
    if result.success or result.dry_run or not plan.moves:
        return "none"
    try:
        from fantasy_gm.nudge.missed import week_kickoff

        now = now or datetime.utcnow()
        try:
            slots = adapter.get_raw_lineup_slots(team_id, record.week, record.season)
            missing = [m for m in plan.moves if slots.get(m.player_id) != m.to_slot]
            read_back = "missing" if missing else "landed"
        except Exception:
            missing = list(plan.moves)  # nothing could be checked: every move may be needed
            read_back = "unreadable"

        outcome = store.get(record.id).outcome or {}
        if read_back == "landed":
            store.record_outcome(record.id, {**outcome, "write_landed": {
                "at": now.isoformat(), "error": result.error}})
            return "landed"

        # Only what still needs doing — a move that landed is not an instruction.
        moves = [_step_for(plan, m) for m in missing]
        minutes = (week_kickoff(record.season, record.week) - now).total_seconds() / 60
        failure = {
            "at": now.isoformat(), "error": result.error, "moves": moves,
            "read_back": read_back, "notified": False, "notify_error": None,
            "minutes_to_kickoff": round(minutes, 1),
        }
        if minutes > 0:
            checked = ("" if read_back == "missing"
                       else "Couldn't check the lineup afterwards. ")
            try:
                notifier.send(
                    f"Lineup write failed. {checked}Set it by hand: " + "; ".join(moves),
                    f"Kickoff in {format_minutes(minutes)}")
                failure["notified"] = True
            except Exception as exc:
                failure["notify_error"] = f"{type(exc).__name__}: {exc}"
        store.record_outcome(record.id, {**outcome, "write_failure": failure})
        return "notified" if failure["notified"] else "recorded"
    except Exception as exc:  # reporting a failure must never become a second one
        print(f"failed-write report skipped: {type(exc).__name__}: {exc}", file=sys.stderr)
        return "none"
