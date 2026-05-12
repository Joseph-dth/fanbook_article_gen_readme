"""Orchestrator pipeline: wires the chief-editor query() with 4 subagents
and the in-process passage_search MCP server.
"""
from __future__ import annotations

import json
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    TaskNotificationMessage,
    TaskProgressMessage,
    TaskStartedMessage,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    ToolResultBlock,
    UserMessage,
    create_sdk_mcp_server,
    query,
)

from agents import all_subagents
from agents.book_tools import passage_search_tool
from agents.editor_tools import ai_free_review_tool, social_rewrite_tool
from config import Config

ROOT = Path(__file__).resolve().parent
ORCHESTRATOR_PROMPT = (ROOT / "prompts" / "orchestrator.md").read_text(encoding="utf-8")


def _stringify_tool_result(content) -> str:
    """A ToolResultBlock's `content` is either a str or a list of MCP-style
    {type, text} dicts. Concatenate text fields for display."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if "text" in item:
                    parts.append(str(item["text"]))
                else:
                    parts.append(json.dumps(item, ensure_ascii=False))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


def _build_user_prompt(
    topic: str,
    versions: int,
    output_dir: Path,
    slug: str,
    config: Config,
) -> str:
    payload = {
        "topic": topic,
        "versions": versions,
        "output_dir": str(output_dir),
        "slug": slug,
        "version_specs": [
            {"style": s.style, "length": s.length} for s in config.version_specs
        ],
        "default_length": config.default_length,
        "length_tolerance": config.length_tolerance,
        "retrieval": {
            "books_per_article": config.books_per_article,
            "passages_per_book": config.passages_per_book,
        },
        "character": {
            "count": config.character_count,
        },
        "social_post": {
            "enabled": config.social_post.enabled,
            "length": config.social_post.length,
            "platform": config.social_post.platform,
        },
        "review": {
            "enabled": config.review.enabled,
            "iterations": config.review.iterations,
        },
    }
    extra_instructions = (
        "派發給 `角色` agent 時，請在 dispatch prompt 內傳遞 `count = "
        f"{config.character_count}`。\n"
        "派發給 `書籍` agent 時，請在 dispatch prompt 內傳遞 `books_per_article = "
        f"{config.books_per_article}`、`passages_per_book = {config.passages_per_book}`。\n"
        "派發每個 `寫手` 時，依 system prompt Step 3 的規則：若 input.social_post.enabled "
        "為 true，把 `social_post` 物件塞進 dispatch JSON（寫手會自己派社群 agent）；"
        "若 input.review.enabled 為 true，把 `review` 物件塞進 dispatch JSON（寫手會自己派審查 agent）。"
    )

    return (
        f"以下是這次任務的輸入：\n\n"
        f"```json\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n```\n\n請依 system prompt 的流程執行：派發 4 個研究 agent → 規劃 N 版差異化 → 平行 fan-out N 個寫手。\n\n"
        + extra_instructions
    )


async def run_pipeline(
    topic: str,
    versions: int,
    output_dir: Path,
    slug: str,
    config: Config,
    *,
    verbose: bool = True,
) -> str:
    """Run the orchestrator and return its final text result."""

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / slug).mkdir(parents=True, exist_ok=True)

    book_rag_server = create_sdk_mcp_server(
        name="bookrag",
        version="0.1.0",
        tools=[passage_search_tool],
    )
    editor_server = create_sdk_mcp_server(
        name="editor",
        version="0.1.0",
        tools=[ai_free_review_tool, social_rewrite_tool],
    )

    options = ClaudeAgentOptions(
        system_prompt=ORCHESTRATOR_PROMPT,
        model=config.models.get("orchestrator", "opus"),
        cwd=str(ROOT),
        agents=all_subagents(
            config.models,
            include_social=False,  # social now an MCP tool the writer calls
            include_reviewer=False,  # reviewer too
        ),
        mcp_servers={"bookrag": book_rag_server, "editor": editor_server},
        allowed_tools=[
            "Agent",
            "Read",
            "Write",
            "mcp__bookrag__passage_search",
            "mcp__editor__ai_free_review",
            "mcp__editor__social_rewrite",
        ],
        permission_mode="bypassPermissions",
        setting_sources=[],  # don't inject CLAUDE.md / .claude settings into orchestrator or subagents
    )

    user_prompt = _build_user_prompt(topic, versions, output_dir, slug, config)

    final_text = ""
    last_tool_per_task: dict[str, str | None] = {}
    task_labels: dict[str, str] = {}  # task_id -> human label (TaskNotification has no description field)
    agent_dispatches: dict[str, str] = {}  # tool_use_id -> subagent name (for surfacing dispatch results)
    async for msg in query(prompt=user_prompt, options=options):
        # Order matters: TaskStarted/Progress/Notification subclass SystemMessage,
        # so check the specific types first.
        if isinstance(msg, TaskStartedMessage):
            label = msg.description or msg.task_type or msg.task_id
            task_labels[msg.task_id] = label
            if verbose:
                print(f"[subagent ▶ {label}] started", flush=True)
        elif isinstance(msg, TaskProgressMessage):
            label = msg.description or task_labels.get(msg.task_id, msg.task_id)
            if verbose:
                tool = msg.last_tool_name
                prev = last_tool_per_task.get(msg.task_id)
                if tool and tool != prev:
                    last_tool_per_task[msg.task_id] = tool
                    print(f"[subagent · {label}] tool={tool}", flush=True)
        elif isinstance(msg, TaskNotificationMessage):
            if verbose:
                label = task_labels.get(msg.task_id, msg.task_id)
                status = getattr(msg.status, "value", msg.status)
                print(f"[subagent ◀ {label}] {status} — {msg.summary}", flush=True)
                # Surface the subagent's full output by reading the transcript file
                # (only when the SDK actually provided a real file path).
                out_path_str = (msg.output_file or "").strip()
                if out_path_str and out_path_str not in (".", "/"):
                    out_path = Path(out_path_str)
                    if out_path.is_file():
                        try:
                            content = out_path.read_text(encoding="utf-8").strip()
                            if content:
                                print(f"--- subagent output ({label}) ---\n{content}\n--- end ---", flush=True)
                        except Exception as e:
                            print(f"  (could not read {out_path}: {e})", flush=True)
        elif isinstance(msg, SystemMessage):
            if verbose and msg.subtype not in ("task_started", "task_progress", "task_notification"):
                print(f"[system] {msg.subtype}", flush=True)
        elif isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    if verbose:
                        print(f"[orchestrator] {block.text}", flush=True)
                    final_text = block.text
                elif isinstance(block, ToolUseBlock):
                    name = block.name
                    if name == "Agent":
                        sub = (block.input or {}).get("subagent_type") or (block.input or {}).get("agent_type")
                        agent_dispatches[block.id] = str(sub) if sub else "?"
                        if verbose:
                            print(f"[tool] dispatch -> {sub}", flush=True)
                    elif verbose and name == "Write":
                        path = (block.input or {}).get("file_path", "?")
                        print(f"[tool] Write -> {path}", flush=True)
                    elif verbose and name == "Read":
                        path = (block.input or {}).get("file_path", "?")
                        print(f"[tool] Read  -> {path}", flush=True)
                    elif verbose:
                        print(f"[tool] {name}", flush=True)
                elif isinstance(block, ThinkingBlock):
                    pass
                elif isinstance(block, ToolResultBlock):
                    pass
        elif isinstance(msg, UserMessage):
            # Tool results (including Agent dispatch results) come back as UserMessage blocks.
            for block in msg.content:
                if not isinstance(block, ToolResultBlock):
                    continue
                sub = agent_dispatches.get(block.tool_use_id)
                if not sub or not verbose:
                    continue
                text = _stringify_tool_result(block.content)
                if text.strip():
                    print(
                        f"--- 子 agent 回傳 ({sub}) ---\n{text.strip()}\n--- end ({sub}) ---",
                        flush=True,
                    )
        elif isinstance(msg, ResultMessage):
            if verbose:
                print(
                    f"[result] turns={msg.num_turns} cost_usd={msg.total_cost_usd:.4f} duration={msg.duration_ms}ms",
                    flush=True,
                )
            if msg.result and not final_text:
                final_text = msg.result

    return final_text
