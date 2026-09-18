"""Web test fixtures.

Two things make this layer testable and they are both deliberate:

  * `WebSettings` is injectable, so `db_path` and `cache_dir` point at tmp_path
    and no test ever touches the real decision log or the real cache.
  * the *adapter* is faked, not HTTP. Fixture `Roster` / `TeamStanding` /
    `Matchup` objects go in and the templates render them, which is what we
    actually want to assert. One respx-based test covers real HTTP separately.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from fantasy_gm.models import (
    LeagueSettings,
    Matchup,
    Platform,
    Player,
    PlayerStatus,
    Position,
    Roster,
    RosterPlayer,
    RosterSlot,
    ScoringRule,
    ScoringRules,
    TeamScore,
    TeamStanding,
    WaiverType,
)
from fantasy_gm.web import deps
from fantasy_gm.web.app import create_app
from fantasy_gm.web.settings import WebSettings

STARTER_SLOTS = [
    (Position.QB, 1), (Position.RB, 2), (Position.WR, 2),
    (Position.TE, 1), (Position.FLEX, 1), (Position.DST, 1), (Position.K, 1),
]

# name, position, nfl_team, projection, status
SQUAD = [
    ("Josh Allen",      Position.QB,  "BUF", 22.1, PlayerStatus.ACTIVE),
    ("Bijan Robinson",  Position.RB,  "ATL", 15.8, PlayerStatus.ACTIVE),
    ("Breece Hall",     Position.RB,  "NYJ", 13.2, PlayerStatus.QUESTIONABLE),
    ("Ja'Marr Chase",   Position.WR,  "CIN", 18.4, PlayerStatus.ACTIVE),
    ("Puka Nacua",      Position.WR,  "LAR", 14.0, PlayerStatus.ACTIVE),
    ("Trey McBride",    Position.TE,  "ARI", 11.5, PlayerStatus.ACTIVE),
    ("Jaylen Waddle",   Position.WR,  "MIA", 12.9, PlayerStatus.ACTIVE),
    ("Ravens D/ST",     Position.DST, "BAL",  8.0, PlayerStatus.ACTIVE),
    ("Harrison Butker", Position.K,   "KC",   8.6, PlayerStatus.ACTIVE),
    ("Rome Odunze",     Position.WR,  "CHI",  9.7, PlayerStatus.ACTIVE),
    ("Tank Bigsby",     Position.RB,  "JAX",  6.1, PlayerStatus.OUT),
]

FLEX_ELIGIBLE = {Position.RB, Position.WR, Position.TE}


def _eligible(position: Position) -> list[Position]:
    if position in FLEX_ELIGIBLE:
        return [position, Position.FLEX]
    return [position]


@pytest.fixture
def league_settings() -> LeagueSettings:
    slots: list[RosterSlot] = []
    for position, count in STARTER_SLOTS:
        for i in range(count):
            slots.append(RosterSlot(slot_id=f"{position.value}_{i}", position=position,
                                    is_starter=True))
    for i in range(4):
        slots.append(RosterSlot(slot_id=f"BE_{i}", position=Position.BENCH, is_starter=False))
    return LeagueSettings(
        platform=Platform.ESPN,
        league_id="1660218687",
        season=2026,
        team_count=12,
        roster_slots=slots,
        scoring_rules=ScoringRules(rules=[ScoringRule(stat="53", points=1.0)]),
        waiver_type=WaiverType.ROLLING,
        playoff_start_week=15,
        playoff_weeks=[15, 16, 17],
        regular_season_weeks=list(range(1, 15)),
    )


@pytest.fixture
def projections() -> dict[str, float]:
    return {str(100 + i): proj for i, (_, _, _, proj, _) in enumerate(SQUAD)}


@pytest.fixture
def roster() -> Roster:
    """Team 8's roster. Deliberately sub-optimal: the OUT player starts at RB
    and the higher-projecting WR sits, so the optimizer has something to say."""
    players: list[RosterPlayer] = []
    # slot assignment that is legal but wrong — Bigsby (OUT) starts over Hall
    slots = [Position.QB, Position.RB, Position.BENCH, Position.WR, Position.WR,
             Position.TE, Position.FLEX, Position.DST, Position.K,
             Position.BENCH, Position.RB]
    for i, (name, position, team, _, status) in enumerate(SQUAD):
        players.append(RosterPlayer(
            player=Player(
                platform_id=str(100 + i), name=name, position=position,
                eligible_positions=_eligible(position), nfl_team=team, status=status,
            ),
            slot=slots[i],
            is_starter=slots[i] != Position.BENCH,
        ))
    return Roster(team_id="8", team_name="Junedi", owner_name="Omer Junedi",
                  players=players, week=3, season=2026)


# The opponent's lineup. Needed because the live matchup total is summed from
# both rosters rather than taken from ESPN's `totalPoints`, which reads 0.0.
OPPONENT_SQUAD = [
    ("Patrick Mahomes", Position.QB,  "KC",  21.0, PlayerStatus.ACTIVE),
    ("Saquon Barkley",  Position.RB,  "PHI", 17.5, PlayerStatus.ACTIVE),
    ("De'Von Achane",   Position.RB,  "MIA", 13.0, PlayerStatus.ACTIVE),
    ("CeeDee Lamb",     Position.WR,  "DAL", 16.0, PlayerStatus.ACTIVE),
    ("Garrett Wilson",  Position.WR,  "NYJ", 12.0, PlayerStatus.ACTIVE),
    ("George Kittle",   Position.TE,  "SF",  10.5, PlayerStatus.ACTIVE),
    ("Chris Olave",     Position.WR,  "NO",  11.0, PlayerStatus.ACTIVE),
    ("Bills D/ST",      Position.DST, "BUF",  7.0, PlayerStatus.ACTIVE),
    ("Jake Bates",      Position.K,   "DET",  8.0, PlayerStatus.ACTIVE),
]


@pytest.fixture
def opponent_projections() -> dict[str, float]:
    return {str(200 + i): proj for i, (_, _, _, proj, _) in enumerate(OPPONENT_SQUAD)}


@pytest.fixture
def opponent_roster() -> Roster:
    slots = [Position.QB, Position.RB, Position.RB, Position.WR, Position.WR,
             Position.TE, Position.FLEX, Position.DST, Position.K]
    players = []
    for i, (name, position, team, _, status) in enumerate(OPPONENT_SQUAD):
        players.append(RosterPlayer(
            player=Player(
                platform_id=str(200 + i), name=name, position=position,
                eligible_positions=_eligible(position), nfl_team=team, status=status,
            ),
            slot=slots[i],
            is_starter=True,
        ))
    return Roster(team_id="6", team_name="Team Six", owner_name="",
                  players=players, week=3, season=2026)


@pytest.fixture
def standings() -> list[TeamStanding]:
    rows = [
        ("8", "Junedi", 2, 0, 241.6, 198.2, 1),
        ("6", "Team Six", 1, 1, 219.4, 210.0, 5),
        ("3", "Gridiron Gang", 0, 2, 180.1, 244.8, 11),
    ]
    return [
        TeamStanding(team_id=tid, team_name=name, wins=w, losses=l,
                     points_for=pf, points_against=pa, playoff_seed=seed)
        for tid, name, w, l, pf, pa, seed in rows
    ]


@pytest.fixture
def matchup() -> Matchup:
    return Matchup(
        week=3, season=2026,
        home=TeamScore(team_id="8", team_name="8", projected_score=118.4),
        away=TeamScore(team_id="6", team_name="6", projected_score=104.7),
        is_complete=False,
    )


class FakeAdapter:
    """Stands in for ESPNAdapter. Records calls so tests can assert on caching."""

    def __init__(self, roster, league_settings, standings, matchup, projections,
                 opponent_roster=None):
        self.league_id = "1660218687"
        self._roster = roster
        self._opponent_roster = opponent_roster
        self._settings = league_settings
        self._standings = standings
        self._matchup = matchup
        self._projections = projections
        self.calls: list[str] = []
        self.cached_at = datetime(2026, 9, 17, 14, 2).timestamp()

    # -- reads ------------------------------------------------------------
    def get_league_settings(self, season: int):
        self.calls.append("get_league_settings")
        return self._settings

    def get_current_week(self, season: int) -> int:
        self.calls.append("get_current_week")
        return 3

    def get_roster(self, team_id: str, week: int, season: int, fresh: bool = False):
        self.calls.append("get_roster")
        if team_id == self._roster.team_id:
            return self._roster
        return Roster(team_id=team_id, team_name=f"Team {team_id}",
                      owner_name="", players=[], week=week, season=season)

    def get_all_rosters(self, week: int, season: int, fresh: bool = False):
        self.calls.append("get_all_rosters_fresh" if fresh else "get_all_rosters")
        rosters = [self._roster]
        if self._opponent_roster is not None:
            rosters.append(self._opponent_roster)
        return rosters

    def get_standings(self, season: int):
        self.calls.append("get_standings")
        return self._standings

    def get_matchup(self, team_id: str, week: int, season: int):
        self.calls.append("get_matchup")
        return self._matchup

    def get_projections(self, week: int, season: int):
        self.calls.append("get_projections")
        return dict(self._projections)

    def get_raw_lineup_slots(self, team_id: str, week: int, season: int):
        self.calls.append("get_raw_lineup_slots")
        espn = {Position.QB: 0, Position.RB: 2, Position.WR: 4, Position.TE: 6,
                Position.DST: 16, Position.K: 17, Position.FLEX: 23,
                Position.BENCH: 20, Position.IR: 21}
        return {rp.player.platform_id: espn[rp.slot] for rp in self._roster.players}

    def get_free_agents(self, week, season, position_filter=None):
        return []

    def get_transactions(self, week, season):
        return []


@pytest.fixture
def fake_adapter(roster, league_settings, standings, matchup, projections,
                 opponent_roster, opponent_projections):
    return FakeAdapter(roster, league_settings, standings, matchup,
                       {**projections, **opponent_projections},
                       opponent_roster=opponent_roster)


def lock_starter(roster_obj, position: Position, actual: float):
    """Mark the first starter at `position` as having played, and return them.

    Selecting by position rather than by player name keeps these tests from
    depending on who happens to be in the fixture squad.
    """
    for rp in roster_obj.players:
        if rp.is_starter and rp.slot == position:
            rp.is_locked = True
            rp.actual_points = actual
            return rp
    raise AssertionError(f"no starter in slot {position}")


def starter_total(roster_obj, projections_map) -> float:
    """What the page should show: banked points where a game is done,
    projections everywhere else. Mirrors `core.optimizer.live_score`."""
    total = 0.0
    for rp in roster_obj.players:
        if not rp.is_starter:
            continue
        total += (rp.actual_points if rp.actual_points is not None
                  else projections_map.get(rp.player.platform_id, 0.0))
    return total


@pytest.fixture
def web_settings(tmp_path) -> WebSettings:
    return WebSettings(
        league_id="1660218687", team_id="8", season=2026, week=3,
        db_path=tmp_path / "decisions.db",
        cache_dir=tmp_path / "cache",
    )


@pytest.fixture
def app(web_settings, fake_adapter):
    application = create_app(web_settings)
    application.state.adapter = fake_adapter
    application.state.executor.adapter = fake_adapter
    application.dependency_overrides[deps.get_adapter] = lambda: fake_adapter
    return application


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


@pytest.fixture
def store(web_settings):
    from fantasy_gm.db.store import DecisionStore
    return DecisionStore(web_settings.db_path)
