"""App factory and static assets."""
from __future__ import annotations

from fantasy_gm.web.settings import WebSettings


def test_root_redirects_to_team(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/team"


def test_stylesheet_is_served(client):
    resp = client.get("/static/app.css")
    assert resp.status_code == 200
    assert "--chyron" in resp.text


def test_htmx_is_vendored_not_a_cdn_link(client):
    """No CDN and no build step: htmx ships in the package."""
    resp = client.get("/static/htmx.min.js")
    assert resp.status_code == 200
    assert len(resp.content) > 10_000


def test_sse_extension_is_vendored(client):
    assert client.get("/static/sse.js").status_code == 200


def test_settings_resolve_against_repo_root_not_cwd(tmp_path):
    """The server must not depend on the directory it was launched from."""
    settings = WebSettings(repo_root=tmp_path)
    assert settings.db_path == tmp_path / "data" / "decisions.db"
    assert settings.cache_dir == tmp_path / "data" / "cache" / "espn"


def test_settings_accept_explicit_paths(tmp_path):
    settings = WebSettings(db_path=tmp_path / "d.db", cache_dir=tmp_path / "c")
    assert settings.db_path == tmp_path / "d.db"
    assert settings.cache_dir == tmp_path / "c"


def test_favicon_is_served_and_vendored(client):
    resp = client.get("/static/favicon.svg")
    assert resp.status_code == 200
    assert "svg" in resp.headers["content-type"]
    # Built from the same tokens as the chyron, not a stock glyph.
    assert "#002E5D" in resp.text
    assert "#FFC300" in resp.text


def test_pages_link_the_favicon(client):
    assert 'href="/static/favicon.svg"' in client.get("/team").text


def test_raster_favicon_fallbacks_exist(client):
    """Not every context takes an SVG icon."""
    for path in ("/static/favicon-32.png", "/static/apple-touch-icon.png"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
