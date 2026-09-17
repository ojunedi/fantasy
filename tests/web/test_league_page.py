"""The league view: standings, matchups, expandable rosters."""
from __future__ import annotations

import pytest


@pytest.fixture
def page(client):
    resp = client.get("/league")
    assert resp.status_code == 200, resp.text
    return resp.text


def test_standings_render_server_side(page):
    """The default tab must not need a second request to show anything."""
    assert "Junedi" in page
    assert "Gridiron Gang" in page
    assert "241.6" in page


def test_standings_are_ranked_by_seed(page):
    assert page.index("Junedi") < page.index("Team Six") < page.index("Gridiron Gang")


def test_records_render_as_w_l(page):
    assert "2-0" in page
    assert "0-2" in page


def test_points_bar_is_scaled_to_the_leader(client, standings):
    text = client.get("/partials/standings").text
    assert 'class="bar ' in text
    assert "width: 100.0%" in text          # the leader's bar is full width


def test_heavy_panels_lazy_load(page):
    """Twelve roster parses must not block the first paint."""
    assert 'hx-get="/partials/rosters"' in page
    assert 'hx-get="/partials/matchups"' in page
    assert "Loading rosters" in page


def test_rosters_partial_expands_my_team_by_default(client):
    text = client.get("/partials/rosters").text
    assert "<details open>" in text
    assert "Josh Allen" in text


def test_rosters_partial_separates_starters_from_bench(client):
    text = client.get("/partials/rosters").text
    assert ">Bench</td>" in text


def test_league_nav_is_marked_current(page):
    assert 'href="/league" aria-current="page"' in page
