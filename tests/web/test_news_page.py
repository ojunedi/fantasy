"""The News page: my players, my teams, around the league.

Stories are in ESPN's shape (athlete and team tags as captured from the live
feed). The fixture roster has Josh Allen (id 100, BUF = ESPN team 2) and
Ja'Marr Chase (id 103, CIN = ESPN team 4).
"""
from __future__ import annotations

import time

import pytest

import fantasy_gm.signals.news as news


def _story(sid, headline, published, athletes=(), teams=()):
    return {"id": sid, "headline": headline, "description": f"About {headline}.",
            "url": f"https://www.espn.com/nfl/story/_/id/{sid}", "published": published,
            "athlete_ids": list(athletes), "team_ids": list(teams)}


@pytest.fixture
def feeds(monkeypatch, roster):
    """league feed + per-team feeds; counts every ESPN request."""
    for rp in roster.players:
        rp.player.nfl_team = {"Josh Allen": "2", "Ja'Marr Chase": "4"}.get(rp.player.name)
    state = {"league": [], "teams": {}, "calls": [], "fail_league": False}

    def fetch(team_id=None, limit=50):
        state["calls"].append(team_id)
        if team_id is None:
            if state["fail_league"]:
                raise ConnectionError("ESPN unreachable")
            return state["league"]
        return state["teams"].get(team_id, [])

    monkeypatch.setattr(news, "fetch_articles", fetch)
    news._feed_cache.clear()
    yield state
    news._feed_cache.clear()


def _section(page: str, heading: str) -> str:
    start = page.index(f"<h2>{heading}</h2>")
    nxt = [page.find("<h2>", start + 1)]
    end = min(i for i in nxt if i > 0) if any(i > 0 for i in nxt) else len(page)
    return page[start:end]


def test_news01_a_story_about_one_of_my_players_is_under_your_players_naming_him(client, feeds):
    feeds["league"] = [_story("1", "Josh Allen limited in practice", "2026-10-31T01:00:00Z",
                              athletes=["100"], teams=["2"])]

    page = client.get("/news").text
    mine = _section(page, "Your players")

    # NEWS-01 THEN it appears under "Your players"
    assert "Josh Allen limited in practice" in mine
    # NEWS-01 AND it names that player
    assert "Your player: " in mine
    assert 'hx-get="/players/100/card"' in mine and ">Josh Allen</a>" in mine


def test_news02_a_story_about_my_players_team_is_under_your_teams(client, feeds):
    feeds["teams"]["4"] = [_story("2", "Bengals sign a practice-squad tackle",
                                  "2026-10-31T00:00:00Z", teams=["4"])]

    page = client.get("/news").text

    # NEWS-02 THEN it appears under "Your teams"
    assert "Bengals sign a practice-squad tackle" in _section(page, "Your teams")
    assert "Bengals sign" not in _section(page, "Your players")


def test_news03_every_other_story_is_around_the_league_and_none_appears_twice(client, feeds):
    shared = _story("3", "Chase questionable with ankle", "2026-10-30T20:00:00Z",
                    athletes=["103"], teams=["4"])
    feeds["league"] = [shared, _story("4", "Commissioner talks expansion",
                                      "2026-10-30T19:00:00Z")]
    feeds["teams"]["4"] = [shared]

    page = client.get("/news").text

    # NEWS-03 THEN each story appears exactly once
    assert page.count("Chase questionable with ankle</a>") == 1
    # NEWS-03 AND the unrelated story is under "Around the league"
    assert "Commissioner talks expansion" in _section(page, "Around the league")


def test_news04_each_story_shows_its_link_summary_source_and_time_newest_first(client, feeds):
    feeds["league"] = [_story("5", "Older league story", "2026-10-30T10:00:00Z"),
                       _story("6", "Newer league story", "2026-10-30T11:00:00Z")]

    page = client.get("/news").text
    league = _section(page, "Around the league")

    # NEWS-04 THEN the newer is listed first
    assert league.index("Newer league story") < league.index("Older league story")
    # NEWS-04 AND each shows its headline linked to the article, its summary, ESPN, and its published time
    assert 'href="https://www.espn.com/nfl/story/_/id/6" target="_blank"' in league
    assert "About Newer league story." in league
    assert "ESPN · " in league
    assert 'href="/news"' in page  # reached from the navigation bar


def test_news05_opening_news_twice_within_15_minutes_asks_espn_once_per_feed(client, feeds):
    client.get("/news")
    first = list(feeds["calls"])

    client.get("/news")

    # NEWS-05 THEN no feed is requested from ESPN again
    assert feeds["calls"] == first
    assert sorted(first, key=str) == sorted([None, "2", "4"], key=str)


def test_news06_an_unreachable_feed_leaves_the_page_standing(client, feeds):
    feeds["fail_league"] = True
    feeds["teams"]["2"] = [_story("7", "Bills activate a linebacker", "2026-10-31T00:00:00Z",
                                  teams=["2"])]

    resp = client.get("/news")

    # NEWS-06 THEN the page renders
    assert resp.status_code == 200
    assert "Bills activate a linebacker" in resp.text
    # NEWS-06 AND it says the news could not be loaded
    assert "Couldn&#39;t load ESPN&#39;s news" in resp.text or "Couldn't load ESPN's news" in resp.text


def test_a_feed_entry_older_than_15_minutes_is_read_again(feeds):
    news.cached_articles(now=time.time() - 20 * 60)
    news.cached_articles()
    assert feeds["calls"] == [None, None]


def test_team_and_league_sections_show_the_newest_25_but_my_players_are_never_cut(client, feeds):
    feeds["league"] = ([_story(f"L{i}", f"League story {i:02d}", f"2026-10-30T{i % 24:02d}:00:00Z")
                        for i in range(40)]
                       + [_story(f"P{i}", f"Allen note {i:02d}", "2026-10-29T00:00:00Z",
                                 athletes=["100"]) for i in range(30)])

    page = client.get("/news").text

    assert _section(page, "Around the league").count("<li>") == 25
    assert _section(page, "Your players").count("<li>") == 30
