"""The app serves this machine only, however it was started.

Driven through raw ASGI scopes on the app `create_app` builds with production
settings, so the server address and Host are exactly what uvicorn passes.
"""
from __future__ import annotations

import asyncio

import pytest

from fantasy_gm.web.app import create_app
from fantasy_gm.web.settings import WebSettings


@pytest.fixture
def production_app(tmp_path):
    """No extra local names — what `fantasy-gm-web` and a bare uvicorn both build."""
    app = create_app(WebSettings(db_path=tmp_path / "d.db", cache_dir=tmp_path / "c"))
    reached = []

    @app.get("/__probe")
    def probe():
        reached.append(True)
        return {"ok": True}

    app.state.reached = reached
    return app


def _request(app, server, host, path="/__probe"):
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
             "method": "GET", "scheme": "http", "path": path, "raw_path": path.encode(),
             "query_string": b"", "root_path": "", "server": server,
             "client": (server[0], 51000), "headers": [(b"host", host.encode())]}
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, body.decode()


def test_localweb01_a_request_from_the_network_is_refused(production_app):
    # Bound to 0.0.0.0; a phone on the Wi-Fi reaches the machine's LAN address.
    status, body = _request(production_app, ("192.168.1.20", 8000), "192.168.1.20:8000")

    # LOCALWEB-01 THEN the response is 403 with a reason saying the app only serves this machine
    assert status == 403
    assert "only serves this machine" in body
    # LOCALWEB-01 AND no route runs
    assert production_app.state.reached == []


def test_localweb02_a_foreign_host_name_on_loopback_is_refused(production_app):
    status, _ = _request(production_app, ("127.0.0.1", 8000), "evil.example:8000")

    # LOCALWEB-02 THEN the response is 403
    assert status == 403
    # LOCALWEB-02 AND no route runs
    assert production_app.state.reached == []


@pytest.mark.parametrize("server,host", [
    (("127.0.0.1", 8000), "localhost:8000"),
    (("127.0.0.1", 8000), "127.0.0.1:8000"),
    (("::1", 8000), "[::1]:8000"),
    (("127.0.0.1", 8000), "localhost"),
])
def test_localweb03_this_machine_is_served_as_today(production_app, server, host):
    status, _ = _request(production_app, server, host)

    # LOCALWEB-03 THEN it is served as before
    assert status == 200
    assert production_app.state.reached == [True]


def test_localweb04_every_refusal_is_logged(production_app, capsys):
    _request(production_app, ("10.0.0.5", 8000), "10.0.0.5:8000")

    # LOCALWEB-04 THEN standard error names the address and the host it arrived with
    err = capsys.readouterr().err
    assert "10.0.0.5" in err
    assert "'10.0.0.5:8000'" in err


def test_a_real_page_is_refused_from_the_network_too(production_app):
    status, _ = _request(production_app, ("192.168.1.20", 8000), "192.168.1.20:8000",
                         path="/history")
    assert status == 403
