"""passage_search: embedding-based retrieval over the chromadb passages index.

Used by:
- the book agent's custom in-process tool (`agents/book.py`)
- direct smoke tests / debugging
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .embed import embed_query
from .store import get_passages_collection


@dataclass
class PassageHit:
    book_id: str
    book_title: str
    source: str  # 'highlights' | 'freeTranscript' | 'vipTranscript'
    char_start: int
    char_end: int
    text: str
    score: float  # cosine similarity (1 - distance)

    def to_dict(self) -> dict:
        return asdict(self)


def passage_search(
    book_ids: list[str],
    query: str,
    top_k: int = 5,
) -> list[PassageHit]:
    """Retrieve top-k passage chunks limited to the given book_ids.

    `query` is free-form text; it is embedded with bge-m3. `book_ids` must be
    folder names under book_data/ (e.g. "1_非暴力溝通").
    """
    if not book_ids:
        return []
    if top_k <= 0:
        return []

    collection = get_passages_collection()
    qvec = embed_query(query)

    where = {"book_id": {"$in": book_ids}} if len(book_ids) > 1 else {"book_id": book_ids[0]}

    res = collection.query(
        query_embeddings=[qvec],
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    hits: list[PassageHit] = []
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    for doc, meta, dist in zip(docs, metas, dists):
        hits.append(
            PassageHit(
                book_id=str(meta.get("book_id", "")),
                book_title=str(meta.get("book_title", "")),
                source=str(meta.get("source", "")),
                char_start=int(meta.get("char_start", 0)),
                char_end=int(meta.get("char_end", 0)),
                text=doc or "",
                score=float(1.0 - dist),
            )
        )
    return hits
