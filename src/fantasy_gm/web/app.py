"""App factory.

`create_app(settings=...)` takes an injectable `WebSettings`, which is what
makes the whole layer testable: tests point `db_path` and `cache_dir` at a
tmp_path and override `deps.get_adapter` with a fake.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from fantasy_gm.execute.espn_api import ESPNApiExecutor
from fantasy_gm.execute.waiver_api import ESPNWaiverApiExecutor
from fantasy_gm.nudge.notify import MacNotifier
from fantasy_gm.web import deps
from fantasy_gm.web.runs import RunManager
from fantasy_gm.web.settings import WebSettings


def create_templates(settings: WebSettings) -> Jinja2Templates:
    templates = Jinja2Templates(directory=str(settings.templates_dir))
    templates.env.trim_blocks = True
    templates.env.lstrip_blocks = True
    from fantasy_gm.web import filters
    templates.env.filters.update(filters.FILTERS)
    from fantasy_gm.web.context import claim_failure_words
    templates.env.globals["failure_words"] = claim_failure_words
    return templates


def create_app(settings: WebSettings | None = None) -> FastAPI:
    settings = settings or WebSettings()

    app = FastAPI(title="Fantasy GM", docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.adapter = deps.build_adapter(settings)
    app.state.executor = ESPNApiExecutor(app.state.adapter)
    app.state.waiver_executor = ESPNWaiverApiExecutor(app.state.adapter)
    app.state.notifier = MacNotifier()
    app.state.reads = deps.ReadCache(settings.read_ttl_seconds)
    app.state.runs = RunManager()
    app.state.templates = create_templates(settings)

    # Serve this machine only, whatever host uvicorn was told to bind (NFR-11).
    from fantasy_gm.web.local_only import LocalOnly
    app.add_middleware(LocalOnly, extra_names=settings.extra_local_names)

    app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")

    from fantasy_gm.web.routes import approve, nudge, pages, partials, runs_routes, trades, waiver
    app.include_router(pages.router)
    app.include_router(partials.router)
    app.include_router(runs_routes.router)
    app.include_router(approve.router)
    app.include_router(trades.router)
    app.include_router(nudge.router)
    app.include_router(waiver.router)

    from fantasy_gm.web.errors import install_error_handlers
    install_error_handlers(app)

    return app


def main() -> None:
    """`fantasy-gm-web` console script — localhost only, one worker.

    Both are load-bearing: the run registry lives in process memory, and the app
    holds ESPN write cookies behind an unauthenticated form.
    """
    import uvicorn

    uvicorn.run("fantasy_gm.web.app:create_app", factory=True,
                host="127.0.0.1", port=8000, workers=1)


if __name__ == "__main__":
    main()
