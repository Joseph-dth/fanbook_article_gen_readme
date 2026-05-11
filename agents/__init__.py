"""Subagent definitions and the in-process MCP tool for book passage search."""
from __future__ import annotations

from pathlib import Path

from claude_agent_sdk import AgentDefinition

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def hotspot_agent(model: str = "haiku") -> AgentDefinition:
    return AgentDefinition(
        description="從 input 主題中拓展關鍵詞、情感鉤子與讀者輪廓。MVP 為 stub，未來接 Thread/Dcard 爬蟲。",
        prompt=_load_prompt("hotspot"),
        tools=["Read"],
        model=model,
    )


def pain_point_agent(model: str = "sonnet") -> AgentDefinition:
    return AgentDefinition(
        description="把表面議題挖到底層卡點，並產出給書籍 agent 用的 search_query。",
        prompt=_load_prompt("pain_point"),
        tools=["Read"],
        model=model,
    )


def character_agent(model: str = "sonnet") -> AgentDefinition:
    return AgentDefinition(
        description="為主題與卡點產出指定數量、立場差異大、口吻能站住的真實角色。",
        prompt=_load_prompt("character"),
        tools=["Read"],
        model=model,
    )


def book_agent(model: str = "opus") -> AgentDefinition:
    """Book agent uses Read (for book_index.json) + passage_search MCP tool."""
    return AgentDefinition(
        description="從本地書庫找回應卡點的智慧；兩階段（LLM 概念選書 → embedding 段落 RAG）。數量由 orchestrator 在 dispatch input 指定。",
        prompt=_load_prompt("book"),
        tools=["Read", "mcp__bookrag__passage_search"],
        model=model,
    )


def writer_agent(model: str = "opus") -> AgentDefinition:
    """Writer agent: takes a fully-planned dispatch JSON from the orchestrator
    and writes one article version, then Writes it to the specified path.
    Each writer runs in its own subagent session so context stays clean across N versions.

    The writer has access to two MCP tools (NOT subagents — SDK forbids subagent-
    in-subagent dispatch):
    - mcp__editor__ai_free_review: runs ai-free-editor review, returns report text
    - mcp__editor__social_rewrite: rewrites the article into a social post
    The writer applies the review report by editing the file itself, and Writes
    the social-post tool's return to the social output path. So each writer is
    still the "owner" of one version (long-form + review iterations + social)."""
    return AgentDefinition(
        description="依總編輯派發的單版規劃寫出一篇長文，並在需要時呼叫審查/社群 MCP 工具迭代修稿與產出社群短文。一個寫手 = 一版的完整 owner。",
        prompt=_load_prompt("writer"),
        tools=[
            "Read",
            "Write",
            "mcp__editor__ai_free_review",
            "mcp__editor__social_rewrite",
        ],
        model=model,
    )


def reviewer_agent(model: str = "sonnet") -> AgentDefinition:
    """Reviewer agent (AI-free editor): scores a piece of Chinese text on 3 dimensions
    (錨/歪/動), flags the 3 worst sentences, suggests rewrites for those, and gives a
    one-line diagnosis. Does NOT rewrite the whole piece — the caller does that."""
    return AgentDefinition(
        description="審查一段中文文字的 AI 味（錨/歪/動三維度）、標出最壞 3 句並給改寫建議。不整篇重寫。",
        prompt=_load_prompt("reviewer"),
        tools=["Read"],
        model=model,
    )


def social_agent(model: str = "sonnet") -> AgentDefinition:
    """Social-post agent: takes a finished article + target length + platform,
    returns a shortened post anchored on a vivid story segment from the original."""
    return AgentDefinition(
        description="把一篇完整長文剪一個有畫面/情緒/張力的故事片段當錨點，改寫成適合貼社群的短版。",
        prompt=_load_prompt("social"),
        tools=["Read"],
        model=model,
    )


def all_subagents(
    models: dict[str, str] | None = None,
    *,
    include_social: bool = False,
    include_reviewer: bool = False,
) -> dict[str, AgentDefinition]:
    """Build subagent definitions, optionally overriding models per agent.

    If `models` is None, each agent uses its built-in default. Keys: hotspot,
    pain_point, character, book, writer, reviewer, social. `社群` is included
    when `include_social=True` (driven by config[social_post].enabled); `審查`
    when `include_reviewer=True` (driven by config[review].enabled).
    """
    m = models or {}
    agents = {
        "熱點": hotspot_agent(m.get("hotspot", "haiku")),
        "卡點": pain_point_agent(m.get("pain_point", "sonnet")),
        "角色": character_agent(m.get("character", "sonnet")),
        "書籍": book_agent(m.get("book", "opus")),
        "寫手": writer_agent(m.get("writer", "opus")),
    }
    if include_reviewer:
        agents["審查"] = reviewer_agent(m.get("reviewer", "sonnet"))
    if include_social:
        agents["社群"] = social_agent(m.get("social", "sonnet"))
    return agents
