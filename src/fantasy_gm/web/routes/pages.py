"""Full-page GET handlers.

Every handler here is a plain `def`, not `async def`, so Starlette runs it in
its threadpool and the synchronous adapter calls never block the event loop.
Only the SSE endpoint in `runs_routes.py` is async.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter()


@router.get("/", include_in_schema=False)
def index() -> RedirectResponse:
    return RedirectResponse("/team", status_code=302)
