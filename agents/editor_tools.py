"""In-process MCP tools the writer uses inline (no subagent dispatch).

Why these are tools instead of subagents:
- Claude Agent SDK forbids a subagent from dispatching another subagent
  ("Task is not available inside subagents"). So the writer cannot fan out to
  審查 / 社群 subagents. We expose those flows as MCP tools instead — from
  the SDK's perspective these are plain function calls, not agent dispatch.
- Each tool internally runs an isolated `query()` with the relevant prompt
  (ai-free-editor / social), so authentication piggy-backs on the same SDK
  credentials as the outer pipeline (no separate ANTHROPIC_API_KEY needed).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
    tool,
)

ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = ROOT / "prompts"


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


async def _ask_via_sdk(*, system_prompt: str, user_prompt: str, model: str) -> str:
    """One-shot query via the SDK. Returns the final assistant text.

    Uses no tools, no subagents — just system_prompt + a single user message.
    Same auth path as the outer pipeline, so it works whether the user has
    ANTHROPIC_API_KEY set or is logged in via Claude Code CLI.
    """
    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=model,
        cwd=str(ROOT),
        permission_mode="bypassPermissions",
        # No allowed_tools — we want a pure text response.
    )

    final_text = ""
    async for msg in query(prompt=user_prompt, options=options):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    final_text = block.text
        elif isinstance(msg, ResultMessage):
            if msg.result and not final_text:
                final_text = msg.result
    return final_text.strip()


# ── ai-free editor (審查) ─────────────────────────────────────────────
@tool(
    "ai_free_review",
    "對一段中文文字做 AI 味審查（錨/歪/動三維度評分 + 最壞 3 句 + 改寫建議 + 一句話總結）。"
    "回傳純文字審查報告 — 不會改寫整篇。"
    "輸入: article=str (要審查的全文), mode=str (narrative_mode，例: 'thread' 時審查者會放寬「歪」標準)。",
    {"article": str, "mode": str},
)
async def ai_free_review_tool(args: dict[str, Any]) -> dict[str, Any]:
    article = args.get("article") or ""
    mode = args.get("mode") or ""

    if not article.strip():
        return {
            "content": [{"type": "text", "text": "ERROR: article is empty"}],
            "is_error": True,
        }

    system = _load_prompt("reviewer")
    # mode hint goes in the user message — never touch reviewer.md itself
    hint = ""
    if mode == "thread":
        hint = (
            "\n\n注意：這篇是 Threads 爆文體（thread 模式），「歪」維度的標準要放寬 — "
            "短句斷得密、節奏跳是這個體裁的特徵，不算 AI 味。「錨」「動」維度照常。"
        )
    user = f"請審查以下中文文字：\n\n{article}{hint}"

    report = await _ask_via_sdk(system_prompt=system, user_prompt=user, model="sonnet")

    # Surface the review report to stdout immediately so the operator can read
    # it while the writer is still iterating, instead of waiting for the writer
    # to complete and echo it back via Step 6.
    snippet = article.strip().splitlines()[0][:40] if article.strip() else ""
    print(
        f"\n[ai_free_review · mode={mode or '?'} · 文章開頭「{snippet}…」]\n{report}\n",
        flush=True,
    )

    return {"content": [{"type": "text", "text": report}]}


# ── social-post rewrite (社群) ────────────────────────────────────────
@tool(
    "social_rewrite",
    "把一篇長文剪一段有畫面/情緒/張力的故事片段當錨點，改寫成適合貼社群的短版。"
    "不是摘要，是把那顆鑽石單獨呈現。回傳純文字社群貼文。"
    "輸入: article=str (完整長文), target_length=int (目標字數), "
    "platform=str (threads/ig/fb/general), original_style=str (長文的 narrative_mode)。",
    {
        "article": str,
        "target_length": int,
        "platform": str,
        "original_style": str,
    },
)
async def social_rewrite_tool(args: dict[str, Any]) -> dict[str, Any]:
    article = args.get("article") or ""
    target_length = int(args.get("target_length") or 300)
    platform = args.get("platform") or "general"
    original_style = args.get("original_style") or ""

    if not article.strip():
        return {
            "content": [{"type": "text", "text": "ERROR: article is empty"}],
            "is_error": True,
        }

    system = _load_prompt("social")
    user = json.dumps(
        {
            "article": article,
            "target_length": target_length,
            "platform": platform,
            "original_style": original_style,
        },
        ensure_ascii=False,
        indent=2,
    )

    post = await _ask_via_sdk(system_prompt=system, user_prompt=user, model="sonnet")
    return {"content": [{"type": "text", "text": post}]}
