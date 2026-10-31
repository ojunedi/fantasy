"""Serve this machine only — however the app was started.

The launcher binds 127.0.0.1, but that is one entry point's default; `uvicorn
--host 0.0.0.0`, an IDE run button or a container would expose an
unauthenticated form holding cookies that can change a real roster (NFR-11).
So the app itself refuses any request that did not arrive on a loopback
address, and any whose Host is not a loopback name — the second stops a
hostile web page reaching 127.0.0.1 through the browser by DNS rebinding.

A refused request never reaches a route, so no gate, read or write runs.
"""
from __future__ import annotations

import ipaddress
import sys

LOOPBACK_NAMES = frozenset({"localhost", "127.0.0.1", "::1"})


def _hostname(host_header: str) -> str:
    host = host_header.strip().lower()
    if host.startswith("["):                       # [::1]:8000
        return host[1:host.find("]")] if "]" in host else host
    if host.count(":") == 1:                       # localhost:8000
        return host.split(":", 1)[0]
    return host                                    # bare name, or bare IPv6


def _loopback_address(server, extra_names) -> bool:
    if not server:
        return False
    address, port = server[0], server[1] if len(server) > 1 else None
    if port is None:                               # a Unix socket is local by nature
        return True
    if address in extra_names:
        return True
    try:
        return ipaddress.ip_address(address).is_loopback
    except ValueError:
        return False


def is_local(scope, extra_names=()) -> tuple[bool, str]:
    """(allowed, host) for an HTTP or WebSocket scope."""
    host = ""
    for name, value in scope.get("headers") or []:
        if name == b"host":
            host = value.decode("latin-1")
            break
    names = LOOPBACK_NAMES | set(extra_names)
    allowed = (_loopback_address(scope.get("server"), extra_names)
               and _hostname(host) in names)
    return allowed, host


class LocalOnly:
    """ASGI middleware: 403 for anything not made on this machine to a loopback name."""

    def __init__(self, app, extra_names=()):
        self.app = app
        self.extra_names = tuple(extra_names)

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        allowed, host = is_local(scope, self.extra_names)
        if allowed:
            return await self.app(scope, receive, send)

        server = scope.get("server")
        print(f"refused request: arrived on {server[0] if server else '?'}, Host {host!r} — "
              f"this app only serves this machine", file=sys.stderr)
        if scope["type"] == "websocket":
            return await send({"type": "websocket.close", "code": 1008})
        body = (b"Refused: Fantasy GM only serves this machine. "
                b"Open it at http://localhost:8000 on the computer running it.\n")
        await send({"type": "http.response.start", "status": 403,
                    "headers": [(b"content-type", b"text/plain; charset=utf-8"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
