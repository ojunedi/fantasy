"""Error handling — chiefly the expired-cookie path.

`ESPNAdapter._fetch` raises `PermissionError` on a 401/403, which in practice
means the `espn_s2` cookie has expired. That is the single most likely failure
in daily use and it has a specific remedy, so it gets its own response rather
than a generic 500: a banner telling you exactly which two values to re-copy.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

REAUTH_MESSAGE = (
    "ESPN rejected the request. Your espn_s2 cookie has most likely expired."
)

REAUTH_STEPS = [
    "Log in to fantasy.espn.com in your browser.",
    "Open DevTools → Application → Cookies → fantasy.espn.com.",
    "Copy the values of SWID and espn_s2.",
    "Update ESPN_SWID and ESPN_S2 in your .env file.",
    "Restart the server so the new cookies are picked up.",
]


class ReauthRequired(Exception):
    """Raised (or converted from PermissionError) when ESPN auth fails."""

    def __init__(self, detail: str = ""):
        self.detail = detail
        super().__init__(detail or REAUTH_MESSAGE)


def render_reauth(request: Request, detail: str = "", status_code: int = 401) -> HTMLResponse:
    templates = request.app.state.templates
    # A fragment request gets just the banner; a full page load gets it framed,
    # so an expired cookie never leaves an HTMX swap target showing stale data.
    partial = request.headers.get("hx-request") == "true"
    return templates.TemplateResponse(
        request,
        "partials/reauth.html" if partial else "reauth.html",
        {"message": REAUTH_MESSAGE, "steps": REAUTH_STEPS, "detail": detail},
        status_code=status_code,
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(PermissionError)
    def _permission_error(request: Request, exc: PermissionError) -> HTMLResponse:
        return render_reauth(request, detail=str(exc))

    @app.exception_handler(ReauthRequired)
    def _reauth_required(request: Request, exc: ReauthRequired) -> HTMLResponse:
        return render_reauth(request, detail=exc.detail)
