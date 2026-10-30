"""Launchd entry point: `python -m fantasy_gm.nudge.cli`.

Reads week and season from environment variables (set by the install script)
or falls back to env defaults. Exits 0 whether or not a nudge fired.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from fantasy_gm.nudge.check import run_check


def main() -> None:
    repo_root = Path(os.environ.get("FANTASY_GM_REPO", Path(__file__).resolve().parents[4]))
    db_path = repo_root / "data" / "decisions.db"

    week_str = os.environ.get("FANTASY_GM_WEEK")
    season_str = os.environ.get("FANTASY_GM_SEASON", "2026")
    threshold_str = os.environ.get("FANTASY_GM_NUDGE_THRESHOLD_MINUTES", "120")

    if week_str is None:
        print("FANTASY_GM_WEEK not set — skipping nudge check", file=sys.stderr)
        sys.exit(0)

    try:
        week = int(week_str)
        season = int(season_str)
        threshold = int(threshold_str)
    except ValueError as exc:
        print(f"Bad env var: {exc}", file=sys.stderr)
        sys.exit(1)

    fired = run_check(db_path, week=week, season=season, threshold_minutes=threshold)
    print("nudge fired" if fired else "no nudge")


if __name__ == "__main__":
    main()
