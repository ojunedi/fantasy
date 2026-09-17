"""The expired-cookie path.

`ESPNAdapter._fetch` raises PermissionError on a 401/403, which in daily use
means espn_s2 has expired. It has a specific remedy, so it gets a specific
response rather than a generic 500.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from fantasy_gm.adapters.espn import ESPNAdapter


@pytest.fixture
def expired(fake_adapter):
    def boom(*args, **kwargs):
        raise PermissionError(
            "ESPN auth failed — your espn_s2 cookie has expired or your league is "
            "private. Re-copy ESPN_SWID and ESPN_S2 from browser DevTools."
        )
    fake_adapter.get_roster = boom
    fake_adapter.get_standings = boom
    return fake_adapter


def test_full_page_gets_the_framed_banner(client, expired):
    resp = client.get("/team")
    assert resp.status_code == 401
    assert "<html" in resp.text
    assert "ESPN needs re-authenticating" in resp.text


def test_the_banner_lists_the_actual_remedy(client, expired):
    text = client.get("/team").text
    for step in ("fantasy.espn.com", "DevTools", "ESPN_SWID", "ESPN_S2", ".env"):
        assert step in text


def test_an_htmx_fragment_gets_only_the_banner(client, expired):
    """An expired cookie must not leave a swap target showing stale data, but it
    also must not inject a whole document into a fragment slot."""
    resp = client.get("/partials/standings", headers={"HX-Request": "true"})
    assert resp.status_code == 401
    assert "<html" not in resp.text
    assert "ESPN needs re-authenticating" in resp.text


def test_espn_detail_is_shown_but_tucked_away(client, expired):
    text = client.get("/team").text
    assert "<details>" in text
    assert "espn_s2" in text


@respx.mock
def test_the_adapter_really_does_raise_on_401(tmp_path):
    """The one end-to-end HTTP test: the contract the web layer depends on."""
    respx.get(url__regex=r".*lm-api-reads.*").mock(return_value=httpx.Response(401))
    adapter = ESPNAdapter(league_id="123", cache_dir=tmp_path / "cache")
    with pytest.raises(PermissionError) as excinfo:
        adapter.get_league_settings(2026)
    assert "espn_s2" in str(excinfo.value)


@respx.mock
def test_a_403_is_treated_the_same_way(tmp_path):
    respx.get(url__regex=r".*lm-api-reads.*").mock(return_value=httpx.Response(403))
    adapter = ESPNAdapter(league_id="123", cache_dir=tmp_path / "cache")
    with pytest.raises(PermissionError):
        adapter.get_league_settings(2026)
