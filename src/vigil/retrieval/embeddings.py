"""Deterministic mock text embeddings.

Hashing is SHA-1-based (NOT Python's ``hash()``, which is PYTHONHASHSEED-
randomized) so embeddings are stable across processes — a bug that bit the IIH
build. The instant ``USE_LLM`` is set, this is swapped for a real
sentence-transformers / API embedder behind the same ``embed_text`` signature.
"""

from __future__ import annotations

import hashlib
import math
import re

DIM = 64
_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def embed_text(text: str, dim: int = DIM) -> list[float]:
    """Deterministic bag-of-tokens embedding, L2-normalized."""

    vec = [0.0] * dim
    for tok in _tokens(text):
        digest = hashlib.sha1(tok.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if (digest[4] & 1) else -1.0
        vec[bucket] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    return max(-1.0, min(1.0, dot))  # both are unit vectors
