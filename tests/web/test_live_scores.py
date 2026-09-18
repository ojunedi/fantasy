"""Live in-week state: banked points, team totals, and locked players.

The motivating bug: the dashboard showed a projection for a player whose game
had already been played, and offered a lineup change ESPN then rejected with
409 TRAN_LINEUP_LOCKED.
"""
from __future__ import annotations

import pytest

from fantasy_gm.models import Position
from tests.web.conftest import lock_starter, starter_total


@pytest.fixture
def played(roster):
    """Jameson Williams's situation: a starter whose game is done, who scored
    well below his projection."""
    lock_starter(roster, Position.WR, actual=5.3)
    return roster


@pytest.fixture
def page(client):
    return client.get("/team").text


@pytest.fixture
def played_page(client, played):
    return client.get("/team").text


# ----------------------------------------------------------- scored points

def test_a_played_player_shows_his_actual_score(played_page):
    assert "5.3" in played_page
    assert "scored" in played_page


def test_an_unplayed_player_shows_no_score(page):
    """Before kickoff there is no actual, and a dash is honest where 0.0 is not."""
    assert "scored" not in page


def test_a_played_player_is_marked_locked(played_page):
    assert "locked" in played_page
    assert "cannot be moved" in played_page


def test_the_projection_is_still_visible_for_context(played_page):
    """His 18.4 projection is what made the call look right; keep it readable."""
    assert "18.4" in played_page


# ------------------------------------------------------------ team totals

def test_both_team_totals_are_shown(page, roster, opponent_roster, fake_adapter):
    proj = fake_adapter._projections
    assert f"{starter_total(roster, proj):.1f}" in page
    assert f"{starter_total(opponent_roster, proj):.1f}" in page


def test_the_headline_is_points_scored_not_a_blend(played_page, roster, opponent_roster,
                                                   fake_adapter):
    """5.3 scored is not 119.2. The big number is what has actually been put on
    the board; the projected final is shown separately as `proj:`."""
    import re
    proj = fake_adapter._projections
    projected_final = starter_total(roster, proj)

    headline = re.search(r'class="chyron__points">([\d.]+)<', played_page).group(1)
    assert headline == "5.3"
    assert headline != f"{projected_final:.1f}"

    assert "proj:" in played_page
    assert f"proj: {projected_final:.1f}" in played_page


def test_each_team_gets_its_own_proj_line(played_page, roster, opponent_roster, fake_adapter):
    proj = fake_adapter._projections
    assert f"proj: {starter_total(roster, proj):.1f}" in played_page
    assert f"proj: {starter_total(opponent_roster, proj):.1f}" in played_page


def test_before_kickoff_the_projection_leads_and_says_so(page):
    """Nobody has scored, so a 0.0 headline would be useless; the projection
    leads and is labelled `proj`, with no per-team proj line to duplicate it."""
    assert "proj:" not in page
    assert "projected margin" in page


def test_a_played_score_changes_my_total(client, roster, opponent_roster, fake_adapter):
    """The total must move to the banked number, not stay on the projection."""
    before = client.get("/team").text
    proj = fake_adapter._projections
    projected_total = starter_total(roster, proj)

    lock_starter(roster, Position.WR, actual=5.3)
    fake_adapter.calls.clear()
    after = client.get("/partials/roster").text

    live_total = starter_total(roster, proj)
    assert live_total < projected_total            # he underperformed
    assert f"{live_total:.1f}" in after


def test_the_roster_note_leads_with_points_scored(played_page):
    assert "Scored" in played_page
    assert "projected final" in played_page


def test_the_chyron_says_live_not_final_mid_week(played_page):
    """Some starters have played and some have not; the label must say so
    rather than claiming a final score."""
    assert ">live<" in played_page
    assert "of your starters played" in played_page


def test_the_played_count_is_my_team_only(played_page, roster):
    """It counted both teams' starters before, so "1 of 18" read as though my
    own lineup had 18 slots."""
    mine = sum(1 for rp in roster.players if rp.is_starter)
    assert f"1 of {mine} of your starters played" in played_page
    assert f"1 of {mine * 2}" not in played_page


def test_the_chyron_says_proj_before_anyone_plays(page):
    assert "projected margin" in page
    assert "starters played" not in page


def test_a_completed_week_reports_a_final_margin(client, roster, opponent_roster):
    for r in (roster, opponent_roster):
        for rp in r.players:
            if rp.is_starter:
                rp.is_locked = True
                rp.actual_points = 10.0
    text = client.get("/team").text
    assert "final margin" in text
    assert ">final<" in text


# --------------------------------------------------- locks in the optimizer

def test_no_change_is_offered_for_a_locked_player(client, roster, projections):
    """Chase is locked at 5.3 while Odunze (9.7) sits — without lock awareness
    the optimizer would want that swap."""
    lock_starter(roster, Position.WR, actual=5.3)
    text = client.get("/partials/roster").text
    rows = [r for r in text.split("<tr") if "Chase" in r]
    assert rows, "Chase should still be listed"
    assert "delta--down" not in rows[0], "a locked player must not be told to bench"
    assert "final" in rows[0]


def test_the_page_explains_why_a_locked_player_is_untouched(client, roster):
    lock_starter(roster, Position.WR, actual=5.3)
    text = client.get("/partials/roster").text
    assert "already played" in text
    assert "ESPN will not move" in text


# ---------------------------------------------------------------- freshness

def test_the_in_week_roster_bypasses_the_disk_cache(client, fake_adapter):
    """Lock state and banked points change at kickoff, so an hour-old roster is
    the wrong thing to render."""
    client.get("/team")
    assert "get_all_rosters_fresh" in fake_adapter.calls


def test_the_memo_still_stops_three_partials_refetching(client, fake_adapter):
    client.get("/team")
    fake_adapter.calls.clear()
    client.get("/partials/roster")
    client.get("/partials/matchups")
    assert fake_adapter.calls.count("get_all_rosters_fresh") == 0


def test_the_matchups_panel_uses_the_same_contract_as_the_chyron(client, roster,
                                                                opponent_roster,
                                                                fake_adapter):
    """It previously showed the projected total labelled "final", which
    contradicted the chyron on the same page."""
    lock_starter(roster, Position.WR, actual=5.3)
    text = client.get("/partials/matchups").text
    proj = fake_adapter._projections
    assert "5.3" in text
    assert f"proj: {starter_total(roster, proj):.1f}" in text
    assert ">live<" in text


def test_the_matchups_panel_says_proj_before_kickoff(client):
    text = client.get("/partials/matchups").text
    assert ">proj<" in text
    assert "final" not in text
