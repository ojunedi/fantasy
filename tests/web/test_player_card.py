"""The player card: photo, ESPN weekly actuals, nflverse season stats, his news.

The fixture league is in week 3, so weeks 1 and 2 are complete.
"""
from __future__ import annotations

import pytest

import fantasy_gm.signals.news as news
import fantasy_gm.web.player_card as card_mod
from fantasy_gm.models import PlayerProjection, Position
from fantasy_gm.signals.sources import nflverse as nv

BIJAN, DEFENSE = "4430807", "-16033"   # -(16000 + 33) = Baltimore


@pytest.fixture
def league(fake_adapter, monkeypatch):
    calls = []

    def get_player_projections(week, season):
        return [PlayerProjection(player_id=BIJAN, player_name="Bijan Robinson", position=Position.RB,
                                 projected_points=20.0, week=week, season=season),
                PlayerProjection(player_id=DEFENSE, player_name="Ravens D/ST", position=Position.DST,
                                 projected_points=8.0, week=week, season=season)]

    def get_actual_scores(week, season):
        calls.append(week)
        return {1: {BIJAN: 21.4}}.get(week, {})

    fake_adapter.get_player_projections = get_player_projections
    fake_adapter.get_actual_scores = get_actual_scores

    class Ids:
        def gsis(self, espn_id):
            return "00-0039000" if espn_id == BIJAN else None
    monkeypatch.setattr(nv, "build_id_map", lambda: Ids())
    monkeypatch.setattr(nv, "season_totals", lambda gsis, season: {
        "carries": 30, "rushing_yards": 151, "rushing_tds": 2, "receptions": 7, "targets": 9,
        "receiving_yards": 54, "receiving_tds": 0, "through_week": 2, "games": 2, "team": "ATL"})
    league_feed = [
        {"id": "1", "headline": "Bijan breaks one", "description": "", "url": "https://espn.com/1",
         "published": "2026-10-30T10:00:00Z", "athlete_ids": [BIJAN], "team_ids": ["1"]},
        {"id": "3", "headline": "Unrelated story", "description": "", "url": "https://espn.com/3",
         "published": "2026-10-30T11:00:00Z", "athlete_ids": ["999"], "team_ids": []},
    ]
    falcons_feed = [   # ATL is ESPN team 1; only his team's feed carries this one
        {"id": "2", "headline": "Bijan and the Falcons line", "description": "", "url": "https://espn.com/2",
         "published": "2026-10-29T10:00:00Z", "athlete_ids": [BIJAN], "team_ids": ["1"]},
    ]
    monkeypatch.setattr(news, "cached_articles",
                        lambda team_id=None: falcons_feed if team_id == "1" else
                        league_feed if team_id is None else [])
    card_mod._completed_weeks.clear()
    yield calls
    card_mod._completed_weeks.clear()


def test_pcard01_a_players_card_shows_his_photo_weekly_points_and_season_stats(client, league):
    html = client.get(f"/players/{BIJAN}/card").text

    # PCARD-01 THEN it shows his ESPN photo
    assert f"https://a.espncdn.com/i/headshots/nfl/players/full/{BIJAN}.png" in html
    # PCARD-01 AND week 1 shows 21.4 and week 2 shows a dash
    assert '<td class="num">21.4</td><td class="num">—</td>' in html
    # PCARD-01 AND his rushing and receiving totals are shown, labelled "through week 2" and nflverse
    assert "30 car, 151 yds, 2 TD" in html
    assert "7/9 tgt, 54 yds, 0 TD" in html
    assert "through week 2 · nflverse" in html


def test_pcard02_a_defense_shows_its_team_logo(client, league):
    html = client.get(f"/players/{DEFENSE}/card").text

    # PCARD-02 THEN it shows the team's logo instead of a photo
    assert "https://a.espncdn.com/i/teamlogos/nfl/500/bal.png" in html
    assert "headshots" not in html


def test_pcard03_recent_headlines_are_those_tagged_with_him(client, league):
    html = client.get(f"/players/{BIJAN}/card").text

    # PCARD-03 THEN the two tagged stories are listed, linked
    assert 'href="https://espn.com/1"' in html and 'href="https://espn.com/2"' in html
    # PCARD-03 AND the other is not
    assert "Unrelated story" not in html


def test_pcard04_names_on_the_team_waiver_and_news_pages_open_the_card(client, store, league,
                                                                       monkeypatch):
    from fantasy_gm.models import DecisionRecord, DecisionType
    store.save(DecisionRecord(
        week=3, season=2026, decision_type=DecisionType.WAIVER, inputs_snapshot={},
        signals_staleness={}, memo="", confidence=1.0,
        recommendation={"scan_state": "recommendation", "candidate": "Jayden Reed",
                        "candidate_id": "900", "displaced_player": "Rome Odunze",
                        "displaced_id": "109", "value_margin": 5.3}))
    allen = {"id": "9", "headline": "Allen limited", "description": "", "url": "https://espn.com/9",
             "published": "2026-10-30T10:00:00Z", "athlete_ids": ["100"], "team_ids": []}
    monkeypatch.setattr(news, "cached_articles", lambda team_id=None: [allen] if team_id is None else [])

    team, waiver, news_page = (client.get(p).text for p in ("/team", "/waiver", "/news"))

    # PCARD-04 THEN each of those names links to that player's card
    assert 'hx-get="/players/100/card"' in team
    assert 'hx-get="/players/900/card"' in waiver and 'hx-get="/players/109/card"' in waiver
    assert 'hx-get="/players/100/card"' in news_page
    assert '<dialog id="player-card"' in team


def test_pcard05_an_unknown_player_gets_a_short_message(client, league):
    resp = client.get("/players/123456789/card")

    # PCARD-05 THEN the response says there is no card for this player
    assert "No card for this player." in resp.text
    # PCARD-05 AND it is not an error page
    assert resp.status_code == 200


def test_pcard06_completed_weeks_are_read_once(client, league):
    client.get(f"/players/{BIJAN}/card")
    first = list(league)

    client.get(f"/players/{DEFENSE}/card")

    # PCARD-06 THEN no completed week's points are read from ESPN again
    assert first == [1, 2]
    assert league == first
