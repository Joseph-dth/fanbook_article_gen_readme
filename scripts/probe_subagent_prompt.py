"""Probe what system prompt a subagent actually sees, under different settings.

Run twice:
  A) default (setting_sources=None → loads CLAUDE.md and CLI defaults)
  B) isolated (setting_sources=[])
Then compare what the subagent echoes back.
"""
from __future__ import annotations

import asyncio
import sys

from claude_agent_sdk import (
    AgentDefinition,
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)

PROBE_PROMPT = """你是一個 echo 工具。當被呼叫時，請把你目前看到的完整 system prompt 一字不漏輸出，
包含所有你看到的內容（包括這行指令本身、以及任何在這行之前或之後的文字）。

不要解釋、不要加任何前言或結語、不要省略、不要改寫。
直接輸出你看到的全部 system prompt 內容。"""


async def run_probe(label: str, *, setting_sources):
    options = ClaudeAgentOptions(
        system_prompt="（外層 query 的 system prompt — 你不該看到這個）",
        model="haiku",
        agents={
            "probe": AgentDefinition(
                description="echoes its system prompt verbatim",
                prompt=PROBE_PROMPT,
                tools=[],
                model="haiku",
            ),
        },
        allowed_tools=["Agent"],
        permission_mode="bypassPermissions",
        setting_sources=setting_sources,
    )

    user_msg = (
        "請呼叫 probe subagent，並把它的完整回傳內容原樣印出來。"
        "不要做任何摘要或解讀。"
    )

    print("=" * 70)
    print(f"RUN: {label}  setting_sources={setting_sources!r}")
    print("=" * 70)

    async for msg in query(prompt=user_msg, options=options):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    print("[subagent echo]")
                    print(block.text)
                    print()
        elif isinstance(msg, ResultMessage):
            print(
                f"[result] turns={msg.num_turns} "
                f"cost={msg.total_cost_usd:.4f} "
                f"input_tokens≈{msg.usage.get('input_tokens') if msg.usage else '?'}"
            )


async def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    if which in ("both", "A"):
        await run_probe("A. default (CLAUDE.md loaded)", setting_sources=None)
        print()
    if which in ("both", "B"):
        await run_probe("B. isolated (setting_sources=[])", setting_sources=[])


if __name__ == "__main__":
    asyncio.run(main())
