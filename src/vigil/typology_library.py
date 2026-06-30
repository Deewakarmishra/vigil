"""The typology library: versioned, content-hashed detection parameters.

Detection thresholds are data, not code. A tenant tunes ``typologies/library.yaml``;
an examiner pins the exact parameters behind a disposition via the ``content_hash``,
which is written into the audit trail. The library always loads — if the YAML is
absent or malformed it falls back to the packaged defaults below, so the demo (and
CI) never depend on a file being present on disk.

This mirrors the routing-policy loader (``policy/loader.py``): parse + hash, with a
safe default. The hash is taken over the *canonical* parameter set (sorted JSON),
so it is stable regardless of YAML key order or comments.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

_LIBRARY_PATH = Path(__file__).resolve().parent / "typologies" / "library.yaml"

# Packaged defaults — the single source of truth if the YAML cannot be read.
DEFAULT_LIBRARY: dict = {
    "version": "2026.06",
    "typologies": {
        "structuring": {
            "window_days": 30,
            "floor": 9000.0,
            "ceiling": 10000.0,
            "min_count": 3,
            "channels": ["cash"],
        },
        "layering": {
            "window_days": 14,
            "min_total_in": 20000.0,
            "movement_ratio": 0.7,
            "min_outflows": 2,
            "require_out_after_in": True,
        },
        "mule": {
            "window_days": 30,
            "max_small_credit": 2000.0,
            "min_distinct_senders": 5,
        },
    },
}


@dataclass(frozen=True)
class TypologyLibrary:
    """An immutable, versioned set of typology parameters + its content hash."""

    version: str
    content_hash: str
    typologies: dict

    def params(self, name: str) -> dict:
        """Return a copy of one typology's parameters (empty dict if unknown)."""

        return dict(self.typologies.get(name, {}))

    @property
    def short_hash(self) -> str:
        return self.content_hash[:12]

    def summary(self) -> dict:
        """Examiner-facing summary for the audit trail / console Sources page."""

        return {
            "version": self.version,
            "content_hash": self.content_hash,
            "typologies": sorted(self.typologies.keys()),
        }


def _canonical_hash(version: str, typologies: dict) -> str:
    blob = json.dumps(
        {"version": version, "typologies": typologies},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def load_library(path: Path | None = None) -> TypologyLibrary:
    """Load the typology library from YAML, falling back to packaged defaults."""

    data = DEFAULT_LIBRARY
    src = path or _LIBRARY_PATH
    if src.exists():
        try:
            loaded = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            loaded = {}
        if isinstance(loaded.get("typologies"), dict) and loaded["typologies"]:
            data = loaded
    version = str(data.get("version", "0"))
    typologies = data.get("typologies", {})
    return TypologyLibrary(
        version=version,
        content_hash=_canonical_hash(version, typologies),
        typologies=typologies,
    )


@lru_cache(maxsize=1)
def get_library() -> TypologyLibrary:
    """Cached process-wide library. Tests clear via ``get_library.cache_clear()``."""

    return load_library()
