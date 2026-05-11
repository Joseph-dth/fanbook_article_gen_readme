"""Compact a raw mindmap.json tree into the book_index.json card form.

Raw mindmap nodes look like {type, label, text, children}; the agent only
needs the human-readable structure (section -> topic -> detail), so we strip
the `type` / `label` noise and keep just the textual hierarchy.
"""
from __future__ import annotations

from typing import Any


def _children_by_type(node: dict[str, Any], child_type: str) -> list[dict[str, Any]]:
    return [c for c in node.get("children", []) or [] if c.get("type") == child_type]


def compact_sections(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sections = []
    for sec in nodes:
        if sec.get("type") != "section":
            continue
        topics = []
        for topic in _children_by_type(sec, "topic"):
            details = [d.get("text", "") for d in _children_by_type(topic, "detail") if d.get("text")]
            topics.append({"title": topic.get("text", ""), "details": details})
        sections.append({
            "label": sec.get("label"),
            "title": sec.get("text", ""),
            "topics": topics,
        })
    return sections


def build_book_card(book_id: str, mindmap: dict[str, Any], transcript: dict[str, Any]) -> dict[str, Any]:
    """Produce the per-book entry that goes into index/book_index.json."""
    return {
        "book_id": book_id,
        "title": transcript.get("name") or mindmap.get("title", ""),
        "subtitle": mindmap.get("subtitle", ""),
        "author": transcript.get("author", ""),
        "tags": transcript.get("tags", []) or [],
        "sections": compact_sections(mindmap.get("nodes", [])),
        "highlights": [h.get("content", "") for h in (transcript.get("highlights") or []) if h.get("content")],
    }


def iter_concept_texts(card: dict[str, Any]):
    """Yield all standalone concept strings (details + highlights) from a card.

    Useful for diagnostics or future fallback embedding-based concept search.
    """
    for sec in card.get("sections", []):
        for topic in sec.get("topics", []):
            for det in topic.get("details", []):
                yield det
    for h in card.get("highlights", []):
        yield h
