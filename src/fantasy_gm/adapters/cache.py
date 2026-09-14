"""
Disk-based response cache with per-entry TTL.

All API responses are cached as JSON files under data/cache/<platform>/<key>.json
alongside a metadata sidecar. Allows offline development and prevents API hammering.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


DEFAULT_TTL_SECONDS = 3600  # 1 hour


class DiskCache:
    def __init__(self, cache_dir: Path, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self.cache_dir = cache_dir
        self.ttl_seconds = ttl_seconds
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _paths(self, key: str) -> tuple[Path, Path]:
        safe = key.replace("/", "__").replace(":", "_")
        return (
            self.cache_dir / f"{safe}.json",
            self.cache_dir / f"{safe}.meta.json",
        )

    def get(self, key: str) -> tuple[Any, float] | None:
        """Return (data, cached_at_timestamp) if cache hit and not expired, else None."""
        data_path, meta_path = self._paths(key)
        if not data_path.exists() or not meta_path.exists():
            return None
        meta = json.loads(meta_path.read_text())
        age = time.time() - meta["cached_at"]
        if age > self.ttl_seconds:
            return None
        return json.loads(data_path.read_text()), meta["cached_at"]

    def set(self, key: str, data: Any) -> None:
        data_path, meta_path = self._paths(key)
        data_path.write_text(json.dumps(data))
        meta_path.write_text(json.dumps({"cached_at": time.time(), "key": key}))

    def get_cached_at(self, key: str) -> float | None:
        """Return epoch timestamp when key was cached, or None."""
        _, meta_path = self._paths(key)
        if not meta_path.exists():
            return None
        return json.loads(meta_path.read_text()).get("cached_at")
