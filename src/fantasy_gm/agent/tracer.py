"""
Live trace output for the agent loop.

Prints tool calls, results, and model transitions to stdout as they happen,
using LangGraph's stream_mode="values" so each node completion is visible
immediately rather than waiting for the full run to finish.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

# ANSI colours (disabled when stdout is not a TTY)
import sys
_TTY = sys.stdout.isatty()

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text

CYAN   = lambda t: _c("36", t)
GREEN  = lambda t: _c("32", t)
YELLOW = lambda t: _c("33", t)
GREY   = lambda t: _c("90", t)
BOLD   = lambda t: _c("1",  t)
DIM    = lambda t: _c("2",  t)


def _strip_think(text: str) -> str:
    """Remove <think>…</think> blocks that qwen3 emits in thinking mode."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _fmt_args(args: dict) -> str:
    """One-line summary of tool args, truncated."""
    try:
        s = json.dumps(args, ensure_ascii=False)
    except Exception:
        s = str(args)
    return s[:120] + "…" if len(s) > 120 else s


def _fmt_result(content: Any) -> str:
    """First 200 chars of a tool result, collapsed to one line."""
    text = content if isinstance(content, str) else json.dumps(content)
    text = text.replace("\n", " ").strip()
    return text[:200] + "…" if len(text) > 200 else text


def print_message(msg: Any, terminal_tools: frozenset[str]) -> None:
    """Print a single message event. Called for each new message in the stream."""
    if isinstance(msg, AIMessage):
        if msg.tool_calls:
            for tc in msg.tool_calls:
                name = tc["name"]
                args = tc.get("args", {})
                label = BOLD(CYAN(f"→ {name}"))
                print(f"  {label}  {DIM(_fmt_args(args))}", flush=True)
        else:
            # Final prose from the model (rare — usually ends via terminal tool)
            text = _strip_think(msg.content if isinstance(msg.content, str) else "")
            if text:
                print(f"  {GREY('✦')} {DIM(text[:300])}", flush=True)

    elif isinstance(msg, ToolMessage):
        name = msg.name or "?"
        result = _fmt_result(msg.content)
        is_terminal = name in terminal_tools
        icon = BOLD(GREEN("✓")) if is_terminal else GREEN("←")
        label = BOLD(name) if is_terminal else name
        print(f"  {icon} {label}  {DIM(result)}", flush=True)


def stream_verbose(
    app,
    input_msg: dict,
    config: dict,
    terminal_tools: frozenset[str],
    label: str = "",
) -> dict:
    """Run the graph with stream_mode='values', printing each new message live.

    Returns the final accumulated state dict (same shape as app.invoke()).
    """
    if label:
        print(f"\n{BOLD(label)}", flush=True)
    print(f"  {DIM('─' * 60)}", flush=True)

    seen = 0
    final_state: dict = {}
    t0 = time.time()

    for state in app.stream(input_msg, config=config, stream_mode="values"):
        final_state = state
        msgs = state.get("messages", [])
        for msg in msgs[seen:]:
            print_message(msg, terminal_tools)
        seen = len(msgs)

    elapsed = time.time() - t0
    tool_count = sum(1 for m in final_state.get("messages", []) if isinstance(m, ToolMessage))
    print(f"  {DIM('─' * 60)}", flush=True)
    print(f"  {DIM(f'{tool_count} tool calls · {elapsed:.0f}s')}\n", flush=True)
    return final_state
