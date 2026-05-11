"""Build the book_index.json (concept layer) and chromadb passages collection
from book_data/*/.

Usage:
    python scripts/build_index.py                # incremental (skip already-indexed books)
    python scripts/build_index.py --rebuild      # drop and rebuild everything
    python scripts/build_index.py --book 1_非暴力溝通  # single book

Layout this script depends on:
    book_data/<book_id>/<book_id>.json           # transcript
    book_data/<book_id>/<book_id>_mindmap.json   # mindmap tree

Output:
    index/book_index.json                        # concept layer (LLM-readable)
    index/<chromadb files>                       # passage layer
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click

# Make `from rag import ...` work when run as a script.
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from rag.chunker import chunk_text, strip_html  # noqa: E402
from rag.embed import embed_texts  # noqa: E402
from rag.mindmap_pack import build_book_card  # noqa: E402
from rag.store import get_passages_collection, reset_passages  # noqa: E402

BOOK_DATA = _ROOT / "book_data"
INDEX_DIR = _ROOT / "index"
BOOK_INDEX_FILE = INDEX_DIR / "book_index.json"


def _list_book_dirs(filter_book: str | None) -> list[Path]:
    if not BOOK_DATA.exists():
        raise SystemExit(f"book_data/ not found at {BOOK_DATA}")
    dirs = sorted(p for p in BOOK_DATA.iterdir() if p.is_dir() and not p.name.startswith("."))
    if filter_book:
        dirs = [p for p in dirs if p.name == filter_book]
        if not dirs:
            raise SystemExit(f"book {filter_book!r} not found in book_data/")
    return dirs


def _load_book(book_dir: Path) -> tuple[dict, dict] | None:
    book_id = book_dir.name
    mindmap_file = book_dir / f"{book_id}_mindmap.json"
    transcript_file = book_dir / f"{book_id}.json"
    if not mindmap_file.exists() or not transcript_file.exists():
        click.echo(f"  ! skipping {book_id}: missing mindmap or transcript", err=True)
        return None
    with open(mindmap_file, encoding="utf-8") as f:
        mindmap = json.load(f)
    with open(transcript_file, encoding="utf-8") as f:
        transcript = json.load(f)
    return mindmap, transcript


def _passage_records(book_id: str, book_title: str, transcript: dict) -> list[dict]:
    """Yield {id, text, metadata} dicts for chromadb upsert.

    Index the highlights individually (already curated short quotes), then
    index whichever long-form transcript is present (prefer vipTranscript).
    """
    records: list[dict] = []

    for i, h in enumerate(transcript.get("highlights") or []):
        text = (h.get("content") or "").strip()
        if not text:
            continue
        records.append({
            "id": f"{book_id}::highlights::{i}",
            "text": text,
            "metadata": {
                "book_id": book_id,
                "book_title": book_title,
                "source": "highlights",
                "char_start": 0,
                "char_end": len(text),
            },
        })

    long_source = "vipTranscript" if transcript.get("vipTranscript") else "freeTranscript"
    long_text = strip_html(transcript.get(long_source))
    if long_text:
        for i, ch in enumerate(chunk_text(long_text, size=500, overlap=100)):
            records.append({
                "id": f"{book_id}::{long_source}::{i}",
                "text": ch.text,
                "metadata": {
                    "book_id": book_id,
                    "book_title": book_title,
                    "source": long_source,
                    "char_start": ch.char_start,
                    "char_end": ch.char_end,
                },
            })

    return records


def _upsert(collection, records: list[dict], batch_size: int = 64) -> None:
    if not records:
        return
    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]
        texts = [r["text"] for r in batch]
        embeddings = embed_texts(texts, batch_size=batch_size)
        collection.upsert(
            ids=[r["id"] for r in batch],
            embeddings=embeddings,
            documents=texts,
            metadatas=[r["metadata"] for r in batch],
        )


@click.command()
@click.option("--rebuild", is_flag=True, help="Drop and rebuild the chromadb collection.")
@click.option("--book", "filter_book", default=None, help="Index only this book_id.")
def main(rebuild: bool, filter_book: str | None) -> None:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    collection = reset_passages() if rebuild else get_passages_collection()
    existing_ids: set[str] = set()
    if not rebuild:
        try:
            existing_ids = set(collection.get(include=[]).get("ids") or [])
        except Exception:
            existing_ids = set()

    book_dirs = _list_book_dirs(filter_book)
    click.echo(f"Indexing {len(book_dirs)} book(s) from {BOOK_DATA}")

    # Load existing book_index.json so partial re-indexing keeps cards we don't touch.
    existing_index: dict = {"books": []}
    if BOOK_INDEX_FILE.exists() and not rebuild:
        with open(BOOK_INDEX_FILE, encoding="utf-8") as f:
            existing_index = json.load(f)
    cards_by_id: dict[str, dict] = {b["book_id"]: b for b in existing_index.get("books", [])}

    for book_dir in book_dirs:
        book_id = book_dir.name
        loaded = _load_book(book_dir)
        if loaded is None:
            continue
        mindmap, transcript = loaded

        card = build_book_card(book_id, mindmap, transcript)
        cards_by_id[book_id] = card

        records = _passage_records(book_id, card["title"], transcript)
        if not rebuild:
            records = [r for r in records if r["id"] not in existing_ids]
        click.echo(f"  - {book_id}: {len(records)} new passage(s) to embed")
        _upsert(collection, records)

    # Stable order: by numeric prefix when present, else by name.
    def _sort_key(book_id: str):
        prefix = book_id.split("_", 1)[0]
        try:
            return (0, int(prefix), book_id)
        except ValueError:
            return (1, 0, book_id)

    ordered = [cards_by_id[k] for k in sorted(cards_by_id.keys(), key=_sort_key)]
    with open(BOOK_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump({"books": ordered}, f, ensure_ascii=False, indent=2)
    click.echo(f"Wrote {BOOK_INDEX_FILE} ({len(ordered)} books)")
    click.echo(f"chromadb passages collection size: {collection.count()}")


if __name__ == "__main__":
    main()
