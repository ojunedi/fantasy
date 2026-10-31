# Design — refuse-unsafe-start

## Context

`web/app.py:main()` binds 127.0.0.1; `create_app()` enforces nothing. See
`intent.md`.

---

# Build approach

## Where the code goes

| Concern | Location | Pattern it follows |
| --- | --- | --- |
| The check | `src/fantasy_gm/web/local_only.py` — `LocalOnly` ASGI middleware | Plain ASGI wrapper, added in `create_app` so every start path gets it |

## Components

| Component | Action | Notes |
| --- | --- | --- |
| `web/local_only.py` — `LocalOnly`, `is_local(scope, extra_names)` | CREATE | Checks `scope["server"]` (the address the connection arrived on) and the `Host` header |
| `web/app.py` — `create_app` | MODIFY | `app.add_middleware(LocalOnly, ...)` |
| `web/settings.py` — `extra_local_names` | MODIFY | Empty in production; the test suite adds Starlette's `testserver` |
| `tests/web/conftest.py` | MODIFY | `web_settings` sets `extra_local_names=("testserver",)` |
| `tests/web/test_local_only.py` | CREATE | |

## Domain

No aggregate. The check runs before any route, so no gate, read or write is
reachable on a refused request.

Local means: the server address is a loopback IP (`ipaddress.is_loopback`),
or the connection is a Unix socket (`server` port is None), or the server
name is in `extra_local_names`; **and** the `Host` header's hostname (port
and IPv6 brackets stripped) is `localhost`, `127.0.0.1`, `::1`, or in
`extra_local_names`. HTTP and WebSocket scopes are checked; lifespan passes.

## Decisions

| Decision | Chosen | Rejected, and why |
| --- | --- | --- |
| Where | Per request, in the factory-built app | A startup check: the app cannot see the bind address at startup; a per-request check holds however it was started |
| Host check | Yes | Server address only: a browser on this machine visiting a hostile page could still reach 127.0.0.1 by DNS rebinding |
| Auth override | None | No remote use exists; an override is the thing to get wrong |
| Test seam | `extra_local_names` setting, empty by default | Disabling the middleware in tests: the suite would stop proving it is installed |

## Risks

| Risk | Mitigation |
| --- | --- |
| The suite's `testserver` host is refused | `extra_local_names` in the test settings only |
| A reverse proxy on this machine | Still loopback, still `localhost` — served |

---

# Test approach

## Scenario coverage

| Scenario | AC | Level | Test file | Test name | Status |
| --- | --- | --- | --- | --- | --- |
| LOCALWEB-01 | AC-1, AC-3 | integration | `tests/web/test_local_only.py` | `LOCALWEB-01: a request from the network is refused` | required |
| LOCALWEB-02 | AC-2 | integration | `tests/web/test_local_only.py` | `LOCALWEB-02: a foreign host name on loopback is refused` | required |
| LOCALWEB-03 | AC-4 | integration | `tests/web/test_local_only.py` | `LOCALWEB-03: this machine is served as today` | required |
| LOCALWEB-04 | AC-5 | integration | `tests/web/test_local_only.py` | `LOCALWEB-04: every refusal is logged` | required |

Tests drive the app built by `create_app` with production settings (no extra
names) through raw ASGI scopes, so the server address and `Host` are exactly
what uvicorn would pass.

## Fixtures and test data

| Fixture | Why it must be realistic |
| --- | --- |
| ASGI scopes with `server=("192.168.1.20", 8000)` / `("127.0.0.1", 8000)` | What uvicorn sets when bound to 0.0.0.0 |

## NFR verification

| NFR | Budget | Measured how | Where it runs |
| --- | --- | --- | --- |
| NFR-11 | Nothing served beyond this machine | LOCALWEB-01/02 | `pytest` |

## Not covered by automated tests

| What | Why | How it is checked instead |
| --- | --- | --- |
| A real phone on the same Wi-Fi | Needs a second device | Start with `--host 0.0.0.0` once and try it |
