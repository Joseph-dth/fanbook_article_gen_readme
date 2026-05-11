"""In-process MCP tool exposing passage_search to the book subagent.

Wired into the orchestrator via create_sdk_mcp_server (see pipeline.py).
"""
from __future__ import annotations

import json
from typing import Any

from claude_agent_sdk import tool

from rag.search import passage_search


@tool(
    "passage_search",
    "對指定 book_ids 的逐字稿做向量檢索，回傳 top_k 段落（含原文、來源、相似度）。"
    "輸入: book_ids=List[str], query=str, top_k=int (預設 5)。",
    {"book_ids": list, "query": str, "top_k": int},
)
async def passage_search_tool(args: dict[str, Any]) -> dict[str, Any]:
    book_ids = args.get("book_ids") or []
    query = args.get("query") or ""
    top_k = int(args.get("top_k") or 5)

    if not book_ids or not query:
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {"error": "book_ids and query are required", "hits": []},
                        ensure_ascii=False,
                    ),
                }
            ],
            "is_error": True,
        }

    hits = passage_search(book_ids=book_ids, query=query, top_k=top_k)
    payload = {"hits": [h.to_dict() for h in hits]}
    return {
        "content": [
            {"type": "text", "text": json.dumps(payload, ensure_ascii=False)}
        ]
    }
