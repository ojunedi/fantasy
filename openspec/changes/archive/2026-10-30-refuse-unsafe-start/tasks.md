# Tasks — refuse-unsafe-start

## 1. The check

- [x] 1.1 Write `LOCALWEB-01`…`LOCALWEB-04` (integration) in `tests/web/test_local_only.py`, driving the `create_app` app with raw ASGI scopes; clause-annotate (AC-1–AC-5)
- [x] 1.2 Create `web/local_only.py` and add it in `create_app`; add `extra_local_names` to `WebSettings`; set it to `("testserver",)` in the web test settings

## 2. Verification

- [x] 2.1 Run `uv run pytest`
- [x] 2.2 Run `node scripts/trace.mjs check --phase delivery --change refuse-unsafe-start`
