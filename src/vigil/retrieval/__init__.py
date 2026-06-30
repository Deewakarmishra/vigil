"""Retrieval subsystem (deterministic embeddings; production swaps in pg_trgm + pgvector)."""

from vigil.retrieval.embeddings import cosine, embed_text

__all__ = ["cosine", "embed_text"]
