"""SQL-hash cache.

Cache key is a 5-tuple: `(sql_hash, dialect, backend_mode, parser_version, cli_version)`.
Stored on disk under `.gsp-cache/` in the dbt project root by default.

Cache hit semantics:
  - parser_version is recorded in the cached response payload by the GSP/SQLFlow API.
    On cache write we extract it; on cache hit we fast-path return the response.
  - cli_version is OUR version. Bumping cli_version invalidates cache (intentional).
  - SQL is normalized (whitespace + comments stripped) before hashing so semantically
    identical SQL produces a cache hit even with cosmetic differences.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_WHITESPACE = re.compile(r"\s+")


def normalize_sql(sql: str) -> str:
    """Cheap SQL normalization for cache-key stability.

    Strips line/block comments and collapses whitespace. Does NOT alter literals
    or rewrite identifiers — the goal is "two SQL strings that mean the same to
    GSP map to the same hash," not full semantic equivalence.
    """
    s = _LINE_COMMENT.sub("", sql)
    s = _BLOCK_COMMENT.sub(" ", s)
    s = _WHITESPACE.sub(" ", s)
    return s.strip()


def cache_key(
    sql: str,
    dialect: str,
    backend_mode: str,
    parser_version: str,
    cli_version: str,
) -> str:
    """Compute a deterministic cache key from the 5-tuple."""
    payload = "|".join((normalize_sql(sql), dialect, backend_mode, parser_version, cli_version))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class CacheEntry:
    key: str
    response: dict[str, Any]
    parser_version: str


class FileCache:
    """Filesystem-backed cache. One JSON file per key."""

    def __init__(self, root: Path | str = ".gsp-cache"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> dict[str, Any] | None:
        p = self._path(key)
        if not p.is_file():
            self._misses += 1
            return None
        try:
            self._hits += 1
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("cache read failed for %s: %s — treating as miss", p, e)
            self._misses += 1
            return None

    def put(self, key: str, response: dict[str, Any]) -> None:
        p = self._path(key)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(response, separators=(",", ":")), encoding="utf-8")
        except OSError as e:
            logger.warning("cache write failed for %s: %s", p, e)

    def stats(self) -> dict[str, int]:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_pct": int(100 * self._hits / total) if total else 0,
        }

    def _path(self, key: str) -> Path:
        # Two-level hash bucket to avoid one giant directory.
        return self.root / key[:2] / f"{key}.json"

    def __getstate__(self):
        # Cache state is on disk; the in-memory counters are session-scoped.
        return {"root": str(self.root)}

    def __setstate__(self, state):
        self.__init__(state["root"])
