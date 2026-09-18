"""The team page: chyron, roster table, optimizer verdict, staleness."""
from __future__ import annotations

import pytest


@pytest.fixture
def page(client):
    resp = client.get("/team")
    assert resp.status_code == 200, resp.text
    return resp.text


def test_chyron_shows_both_team_totals(page, roster, opponent_roster, fake_adapter):
    """Totals are summed from both rosters, because ESPN's own `totalPoints`
    reads 0.0 for this league even after a game has been played."""
    from tests.web.conftest import starter_total
    proj = fake_adapter._projections
    assert f"{starter_total(roster, proj):.1f}" in page
    assert f"{starter_total(opponent_roster, proj):.1f}" in page


def test_chyron_shows_the_margin_not_a_win_probability(page, roster, opponent_roster,
                                                       fake_adapter):
    """D-017: there is no win-probability function in this repo, so the hero
    must show the margin we actually have and nothing invented."""
    from tests.web.conftest import starter_total
    proj = fake_adapter._projections
    margin = starter_total(roster, proj) - starter_total(opponent_roster, proj)
    assert f"{margin:+.1f}" in page
    assert "margin" in page
    assert "win probability" not in page.lower()
    assert "win %" not in page.lower()


def test_roster_lists_every_player(page, roster):
    import html
    rendered = html.unescape(page)
    for rp in roster.players:
        assert rp.player.name in rendered


def test_projections_are_rendered_to_one_decimal(page):
    assert "22.1" in page
    assert "15.8" in page


def test_bench_divider_separates_the_table(page):
    assert ">Bench</td>" in page


def test_out_player_is_flagged(page):
    """Tank Bigsby is OUT and currently starting — the alert must be visible."""
    assert "status--out" in page
    assert "OUT" in page


def test_optimizer_disagreement_is_surfaced(page):
    """The fixture roster starts an OUT player, so the optimizer must want a swap."""
    assert "swap" in page
    assert ">start<" in page or "delta--up" in page


def test_optimizer_gain_is_shown_as_a_lineup_total(page):
    assert "The optimizer's legal best is" in page


def test_run_button_names_the_week(page):
    assert "Run week 3 lineup" in page


def test_staleness_is_visible(page):
    assert "as of" in page


def test_page_does_not_use_monospace(client):
    """Saira's tabular figures do that job; no monospace anywhere."""
    css = client.get("/static/app.css").text
    assert "monospace" not in css


def test_team_page_survives_a_missing_matchup(client, fake_adapter):
    """A bye week is normal and must not take the page down."""
    def boom(*args, **kwargs):
        raise ValueError("No matchup found")
    fake_adapter.get_matchup = boom
    resp = client.get("/team")
    assert resp.status_code == 200
    assert "No matchup scheduled" in resp.text


def test_expired_cookie_renders_the_reauth_banner(client, fake_adapter):
    def expired(*args, **kwargs):
        raise PermissionError("ESPN auth failed — your espn_s2 cookie has expired")
    fake_adapter.get_roster = expired
    resp = client.get("/team")
    assert resp.status_code == 401
    assert "espn_s2" in resp.text
    assert "DevTools" in resp.text


# ------------------------------------------------------------------ partials

def test_roster_partial_matches_the_page(client):
    fragment = client.get("/partials/roster")
    assert fragment.status_code == 200
    assert "Josh Allen" in fragment.text
    # A fragment, not a document.
    assert "<html" not in fragment.text


def test_refresh_bypasses_the_read_cache(client, fake_adapter):
    client.get("/team")
    fake_adapter.calls.clear()
    resp = client.post("/partials/refresh")
    assert resp.status_code == 200
    assert "get_roster" in fake_adapter.calls


def test_read_cache_collapses_repeat_reads(client, fake_adapter):
    """One page plus its partials must not re-parse the same standings file."""
    client.get("/team")
    fake_adapter.calls.clear()
    client.get("/partials/standings")
    client.get("/partials/standings")
    assert fake_adapter.calls.count("get_standings") == 0


def test_standings_partial_ranks_and_marks_my_team(client):
    text = client.get("/partials/standings").text
    assert "Junedi" in text
    assert "is-mine" in text
    assert "241.6" in text


def test_matchups_partial_renders_both_sides(client):
    text = client.get("/partials/matchups").text
    assert "Junedi" in text
    assert "Team Six" in text


def test_nfl_team_is_an_abbreviation_not_an_espn_id(client, roster):
    """ESPN stores the NFL team as a numeric proTeamId; "14" means nothing to a reader."""
    text = client.get("/partials/roster").text
    assert ">BUF<" in text
    assert ">ATL<" in text
    # the fixture uses real abbreviations, so no bare id should survive either
    assert ">14<" not in text


def test_an_in_flight_lineup_run_is_rendered_on_load(client, app):
    """`run_panel.html` renders `run` while the page carries `active_run`, so
    this include needs an explicit binding — without it a reload mid-run raised
    UndefinedError and lost the trace."""
    run = app.state.runs.create("lineup", 3, 2026, "8", supervised=False)
    app.state.runs.publish(run, {
        "kind": "tool_call", "name": "optimize_lineup", "args": {},
        "display": "{}", "block": False})
    text = client.get("/team").text
    assert "optimize_lineup" in text
    assert f"/runs/{run.id}/stream" in text
