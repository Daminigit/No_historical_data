"""
cache.py — File-based cache for all remote API calls.

Cache key = SHA-256 of the full request payload (dict serialised as sorted JSON).
Each call type stores its cache in a sub-directory: cache/geocode/, cache/distance/, cache/llm/.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

_CACHE_ROOT = Path(__file__).parent / "cache"


def _key(payload: Any) -> str:
    """Return the SHA-256 hex digest of a JSON-serialised payload."""
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def get(namespace: str, payload: Any) -> Any | None:
    """Return the cached value for *payload* in *namespace*, or None on miss."""
    path = _CACHE_ROOT / namespace / (_key(payload) + ".json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def set(namespace: str, payload: Any, value: Any) -> None:  # noqa: A001
    """Write *value* to the cache for *payload* in *namespace*."""
    directory = _CACHE_ROOT / namespace
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (_key(payload) + ".json")
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
