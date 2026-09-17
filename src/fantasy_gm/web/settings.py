"""Web-layer configuration.

Every path the server touches resolves against an explicit `repo_root` rather
than the process cwd. `db/store.py` and `adapters/espn.py` both default to
relative paths, which is fine for a CLI launched from the repo but wrong for a
server — and untestable, since tests need a tmp_path database.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _default_repo_root() -> Path:
    # web/settings.py -> web -> fantasy_gm -> src -> repo root
    return Path(__file__).resolve().parents[3]


@dataclass
class WebSettings:
    league_id: str = field(default_factory=lambda: os.environ.get("ESPN_LEAGUE_ID", "1660218687"))
    team_id: str = field(default_factory=lambda: os.environ.get("ESPN_TEAM_ID", "8"))
    season: int = field(default_factory=lambda: int(os.environ.get("FANTASY_GM_SEASON", "2026")))
    week: int | None = None            # None = derive from the league schedule
    repo_root: Path = field(default_factory=_default_repo_root)
    db_path: Path | None = None
    cache_dir: Path | None = None
    read_ttl_seconds: float = 60.0     # in-process memo; far below the 1h disk cache

    def __post_init__(self) -> None:
        self.repo_root = Path(self.repo_root)
        if self.db_path is None:
            self.db_path = self.repo_root / "data" / "decisions.db"
        if self.cache_dir is None:
            self.cache_dir = self.repo_root / "data" / "cache" / "espn"
        self.db_path = Path(self.db_path)
        self.cache_dir = Path(self.cache_dir)

    @property
    def static_dir(self) -> Path:
        return Path(__file__).resolve().parent / "static"

    @property
    def templates_dir(self) -> Path:
        return Path(__file__).resolve().parent / "templates"
