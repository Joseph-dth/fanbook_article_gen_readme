"""bge-m3 embedding wrapper.

Lazy-loads `BAAI/bge-m3` via sentence-transformers on first use. The model is
~2.3GB and downloads once into the HuggingFace cache. Subsequent loads are
local-only.
"""
from __future__ import annotations

from functools import cache

from sentence_transformers import SentenceTransformer

MODEL_NAME = "BAAI/bge-m3"
EMBED_DIM = 1024


@cache
def get_model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME)


def embed_texts(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Encode a list of strings into bge-m3 embeddings (normalized)."""
    if not texts:
        return []
    model = get_model()
    arr = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=len(texts) > 64,
        convert_to_numpy=True,
    )
    return arr.tolist()


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
