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

from langchain_core.messages import AIMessage, ToolMessage

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
    """Remove <think>…</think> blocks some models emit in thinking mode."""
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


def _text_of(msg: Any) -> str:
    """AIMessage text, tolerating list-of-blocks content, with think-tags stripped."""
    content = msg.content
    if isinstance(content, list):
        content = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return _strip_think(content if isinstance(content, str) else "")


def _content_str(content: Any) -> str:
    return content if isinstance(content, str) else json.dumps(content, indent=2, ensure_ascii=False)


def _print_block(text: str, indent: str = "      ") -> None:
    """Print a multi-line block indented, dimmed."""
    for line in text.splitlines() or [""]:
        print(f"{indent}{DIM(line)}", flush=True)


def _no_response_warning(msg: Any) -> None:
    """The failure mode: model returned neither a tool call nor any text."""
    meta = getattr(msg, "response_metadata", {}) or {}
    fr = meta.get("finish_reason") or meta.get("stop_reason") or "?"
    safety = meta.get("safety_ratings") or meta.get("prompt_feedback")
    usage = getattr(msg, "usage_metadata", None)
    print(f"  {YELLOW('⚠ model returned NO tool call and NO text')}", flush=True)
    print(f"      {DIM(f'finish_reason={fr} · usage={usage}')}", flush=True)
    if safety:
        print(f"      {DIM(f'safety/feedback={safety}')}", flush=True)


def print_message(msg: Any, terminal_tools: frozenset[str], full: bool = False) -> None:
    """Print a single message event. Called for each new message in the stream.

    full=True prints untruncated tool outputs, any model reasoning text, and an
    explicit warning when the model returns nothing (no tool call, no text).
    """
    if isinstance(msg, AIMessage):
        text = _text_of(msg)
        if text:  # reasoning may accompany tool calls, or be the final prose
            print(f"  {GREY('✦')} {DIM(text if full else text[:300])}", flush=True)
        if msg.tool_calls:
            for tc in msg.tool_calls:
                name = tc["name"]
                args = tc.get("args", {})
                print(f"  {BOLD(CYAN(f'→ {name}'))}", flush=True)
                if full:
                    _print_block(_content_str(args))
                else:
                    print(f"      {DIM(_fmt_args(args))}", flush=True)
        elif not text:
            _no_response_warning(msg)

    elif isinstance(msg, ToolMessage):
        name = msg.name or "?"
        is_terminal = name in terminal_tools
        icon = BOLD(GREEN("✓")) if is_terminal else GREEN("←")
        label = BOLD(name) if is_terminal else name
        if full:
            print(f"  {icon} {label}", flush=True)
            _print_block(_content_str(msg.content))
        else:
            print(f"  {icon} {label}  {DIM(_fmt_result(msg.content))}", flush=True)


def stream_verbose(
    app,
    input_msg: dict,
    config: dict,
    terminal_tools: frozenset[str],
    label: str = "",
    full: bool = False,
) -> dict:
    """Run the graph with stream_mode='values', printing each new message live.

    Returns the final accumulated state dict (same shape as app.invoke()).
    """
    if label:
        mode = " · trace=full" if full else ""
        print(f"\n{BOLD(label)}{DIM(mode)}", flush=True)
    print(f"  {DIM('─' * 60)}", flush=True)

    seen = 0
    final_state: dict = {}
    t0 = time.time()

    for state in app.stream(input_msg, config=config, stream_mode="values"):
        final_state = state
        msgs = state.get("messages", [])
        for msg in msgs[seen:]:
            print_message(msg, terminal_tools, full=full)
        seen = len(msgs)

    elapsed = time.time() - t0
    msgs = final_state.get("messages", [])
    tool_count = sum(1 for m in msgs if isinstance(m, ToolMessage))
    reached = any(isinstance(m, ToolMessage) and m.name in terminal_tools for m in msgs)
    status = GREEN("reached terminal tool") if reached else YELLOW("NO terminal tool — will abstain")
    print(f"  {DIM('─' * 60)}", flush=True)
    print(f"  {DIM(f'{tool_count} tool calls · {elapsed:.0f}s · ')}{status}\n", flush=True)
    return final_state
