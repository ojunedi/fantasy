"""Fixtures for the decision-log backup tests.

The awkward snapshot is the important one. A tidy snapshot round-trips
through any implementation, including one that re-serialises it — which is
exactly the corruption LEDGBAK-03 exists to catch. Unsorted keys, unicode,
embedded quotes and a non-UTC timestamp are what make that test able to fail.
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from fantasy_gm.db.store import DecisionStore
from fantasy_gm.models import DecisionRecord, DecisionType


AWKWARD_SNAPSHOT = {
    "zeta_last_alphabetically": 1,
    "roster": [{"name": 'Ja"Marr Chase', "team": "CIN"}, {"name": "Amon-Ra St. Brown"}],
    "note": "projections n'ont pas publié — 中文 — \\backslash\\ and 'quotes'",
    "alpha_first_alphabetically": 2,
    "fetched_at": "2026-09-13T09:30:00-04:00",
}


def decision(week: int, season: int = 2026, snapshot: dict | None = None) -> DecisionRecord:
    return DecisionRecord(
        week=week,
        season=season,
        created_at=datetime(2026, 9, 1, tzinfo=timezone(timedelta(hours=-4))) + timedelta(days=week),
        decision_type=DecisionType.LINEUP,
        inputs_snapshot=AWKWARD_SNAPSHOT if snapshot is None else snapshot,
        signals_staleness={"projections": 12.0},
        recommendation={"starter_player_ids": ["1", "2"]},
        memo=f"week {week} memo",
        confidence=0.7,
    )


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
    )


@pytest.fixture
def remote(tmp_path) -> Path:
    """A real bare repository to push to.

    A mock would agree with whatever the implementation does; a bare repo
    accepts a push or rejects it the way the real one will.
    """
    path = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(path)], check=True)
    return path


@pytest.fixture
def backup_repo(tmp_path, remote, monkeypatch) -> Path:
    path = tmp_path / "backup"
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "user.name", "Test")
    git(path, "remote", "add", "origin", str(remote))
    # The repository starts empty, so give the branch a name before the
    # first push rather than depending on the machine's init.defaultBranch.
    git(path, "checkout", "-q", "-b", "main")
    monkeypatch.setenv("FANTASY_GM_BACKUP_REPO", str(path))
    return path


@pytest.fixture
def store(tmp_path) -> DecisionStore:
    return DecisionStore(tmp_path / "decisions.db")


@pytest.fixture
def live_secrets(monkeypatch) -> dict[str, str]:
    """Cookie- and key-shaped values, so the secret scan can actually fail.

    Placeholders like "SECRET" would be absent from the dump whether or not
    the implementation leaks real ones.
    """
    secrets = {
        "ESPN_S2": "AEBq7%2FxcL9mTn0pQrS1uVwXyZaBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789abcdef",
        "ESPN_SWID": "{1A2B3C4D-5E6F-7A8B-9C0D-1E2F3A4B5C6D}",
        "ANTHROPIC_API_KEY": "sk-ant-api03-ZmFrZWtleWZvcnRlc3Rpbmdvbmx5bm90cmVhbA",
    }
    for key, value in secrets.items():
        monkeypatch.setenv(key, value)
    return secrets


def scorecard(week: int, season: int = 2026):
    from fantasy_gm.models import WeeklyScorecard
    return WeeklyScorecard(
        week=week,
        season=season,
        actual_score=110.0 + week,
        optimal_score=130.0 + week,
        baseline_scores={},
        points_left_on_bench=20.0,
        decision_regret=20.0,
    )


@pytest.fixture(autouse=True)
def _clear_pending_backups():
    """The pending marker is process-wide; don't let it leak between tests."""
    from fantasy_gm.db.store import DecisionStore
    DecisionStore._pending.clear()
    yield
    DecisionStore._pending.clear()


def fake_backtester():
    """A Backtester wired to in-memory league data.

    Deliberately nothing to do with the decision log: the backtest replays
    historical league data and never reads a decision. That is what makes the
    scorecards safe to leave out of the backup, and this fixture is where it
    is visible.
    """
    from fantasy_gm.eval.backtest import Backtester
    from fantasy_gm.models import (
        LeagueSettings, Platform, Player, Position, Roster, RosterPlayer,
        RosterSlot, ScoringRule, ScoringRules, WaiverType,
    )

    starters = [(Position.QB, 1), (Position.RB, 1), (Position.WR, 2)]
    slots = [RosterSlot(slot_id=f"{p.value}_{i}", position=p, is_starter=True)
             for p, n in starters for i in range(n)]
    slots += [RosterSlot(slot_id=f"BE_{i}", position=Position.BENCH, is_starter=False)
              for i in range(2)]
    settings = LeagueSettings(
        platform=Platform.ESPN, league_id="1", season=2026, team_count=12,
        roster_slots=slots,
        scoring_rules=ScoringRules(rules=[ScoringRule(stat="53", points=1.0)]),
        waiver_type=WaiverType.ROLLING, playoff_start_week=15,
        playoff_weeks=[15], regular_season_weeks=list(range(1, 15)),
    )

    def player(pid: str, position: Position) -> Player:
        return Player(platform_id=pid, name=f"P{pid}", position=position,
                      eligible_positions=[position], nfl_team="1")

    roster_players = [
        RosterPlayer(player=player("1", Position.QB), slot=Position.QB, is_starter=True),
        RosterPlayer(player=player("2", Position.RB), slot=Position.RB, is_starter=True),
        RosterPlayer(player=player("3", Position.WR), slot=Position.WR, is_starter=True),
        RosterPlayer(player=player("4", Position.WR), slot=Position.WR, is_starter=True),
        RosterPlayer(player=player("5", Position.RB), slot=Position.BENCH, is_starter=False),
    ]

    class _Platform:
        def get_roster(self, team_id, week, season):
            return Roster(team_id=team_id, team_name="T", owner_name="O",
                          players=roster_players, week=week, season=season)

    return Backtester(
        platform=_Platform(), team_id="8", settings=settings,
        projection_fetcher=lambda week, season: [],
        actual_score_fetcher=lambda week, season: {
            rp.player.platform_id: 10.0 + week for rp in roster_players
        },
    )
