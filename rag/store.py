"""chromadb persistence layer for the `passages` collection."""
from __future__ import annotations

from pathlib import Path

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection

PASSAGES = "passages"

# index/ directory at the project root (sibling of this package).
_DEFAULT_INDEX_DIR = Path(__file__).resolve().parent.parent / "index"


def get_client(index_dir: Path | str | None = None) -> ClientAPI:
    path = Path(index_dir) if index_dir else _DEFAULT_INDEX_DIR
    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(path))


def get_passages_collection(index_dir: Path | str | None = None) -> Collection:
    client = get_client(index_dir)
    return client.get_or_create_collection(
        name=PASSAGES,
        metadata={"hnsw:space": "cosine"},
    )


def reset_passages(index_dir: Path | str | None = None) -> Collection:
    """Drop and recreate the passages collection (used by --rebuild)."""
    client = get_client(index_dir)
    try:
        client.delete_collection(PASSAGES)
    except Exception:
        pass
    return client.get_or_create_collection(
        name=PASSAGES,
        metadata={"hnsw:space": "cosine"},
    )
