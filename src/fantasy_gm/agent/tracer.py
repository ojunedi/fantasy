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
from typing import Any, Callable

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


def _no_response_event(msg: Any) -> dict:
    """The failure mode: model returned neither a tool call nor any text."""
    meta = getattr(msg, "response_metadata", {}) or {}
    return {
        "kind": "no_response",
        "finish_reason": meta.get("finish_reason") or meta.get("stop_reason") or "?",
        "safety": meta.get("safety_ratings") or meta.get("prompt_feedback"),
        "usage": getattr(msg, "usage_metadata", None),
    }


def message_events(msg: Any, terminal_tools: frozenset[str], full: bool = False) -> list[dict]:
    """Structured form of `print_message`: the classification, with no I/O.

    One message can yield several events (reasoning text alongside tool calls),
    so this returns a list. `display` is the already-truncated string the
    terminal renderer prints; `block` marks output that spans several lines.
    """
    events: list[dict] = []

    if isinstance(msg, AIMessage):
        text = _text_of(msg)
        if text:  # reasoning may accompany tool calls, or be the final prose
            events.append({"kind": "ai_text", "text": text,
                           "display": text if full else text[:300]})
        for tc in msg.tool_calls:
            args = tc.get("args", {})
            events.append({
                "kind": "tool_call",
                "name": tc["name"],
                "args": args,
                "display": _content_str(args) if full else _fmt_args(args),
                "block": full,
            })
        if not text and not msg.tool_calls:
            events.append(_no_response_event(msg))

    elif isinstance(msg, ToolMessage):
        name = msg.name or "?"
        events.append({
            "kind": "tool_result",
            "name": name,
            "terminal": name in terminal_tools,
            "display": _content_str(msg.content) if full else _fmt_result(msg.content),
            "block": full,
        })

    return events


def print_event(ev: dict) -> None:
    """Render one event from `message_events` to stdout."""
    kind = ev["kind"]
    if kind == "ai_text":
        print(f"  {GREY('✦')} {DIM(ev['display'])}", flush=True)

    elif kind == "tool_call":
        print(f"  {BOLD(CYAN('→ ' + ev['name']))}", flush=True)
        if ev["block"]:
            _print_block(ev["display"])
        else:
            print(f"      {DIM(ev['display'])}", flush=True)

    elif kind == "tool_result":
        icon = BOLD(GREEN("✓")) if ev["terminal"] else GREEN("←")
        label = BOLD(ev["name"]) if ev["terminal"] else ev["name"]
        if ev["block"]:
            print(f"  {icon} {label}", flush=True)
            _print_block(ev["display"])
        else:
            print(f"  {icon} {label}  {DIM(ev['display'])}", flush=True)

    elif kind == "no_response":
        fr, usage, safety = ev["finish_reason"], ev["usage"], ev["safety"]
        print(f"  {YELLOW('⚠ model returned NO tool call and NO text')}", flush=True)
        print(f"      {DIM(f'finish_reason={fr} · usage={usage}')}", flush=True)
        if safety:
            print(f"      {DIM(f'safety/feedback={safety}')}", flush=True)


def print_message(msg: Any, terminal_tools: frozenset[str], full: bool = False) -> None:
    """Print a single message event. Called for each new message in the stream.

    full=True prints untruncated tool outputs, any model reasoning text, and an
    explicit warning when the model returns nothing (no tool call, no text).
    """
    for ev in message_events(msg, terminal_tools, full=full):
        print_event(ev)


def stream_verbose(
    app,
    input_msg: dict,
    config: dict,
    terminal_tools: frozenset[str],
    label: str = "",
    full: bool = False,
    emit: Callable[[dict], None] | None = None,
) -> dict:
    """Run the graph with stream_mode='values', reporting each new message live.

    With `emit=None` (the CLI path) events are printed to stdout. With an `emit`
    callback each event is handed over as a dict instead and nothing is printed,
    so a non-terminal consumer — the web trace — sees the same classification
    rather than having to parse ANSI back into structure.

    Returns the final accumulated state dict (same shape as app.invoke()).
    """
    if emit is None:
        if label:
            mode = " · trace=full" if full else ""
            print(f"\n{BOLD(label)}{DIM(mode)}", flush=True)
        print(f"  {DIM('─' * 60)}", flush=True)
    else:
        emit({"kind": "start", "label": label, "full": full})

    seen = 0
    final_state: dict = {}
    t0 = time.time()

    for state in app.stream(input_msg, config=config, stream_mode="values"):
        final_state = state
        msgs = state.get("messages", [])
        for msg in msgs[seen:]:
            for ev in message_events(msg, terminal_tools, full=full):
                print_event(ev) if emit is None else emit(ev)
        seen = len(msgs)

    elapsed = time.time() - t0
    msgs = final_state.get("messages", [])
    tool_msgs = [m for m in msgs if isinstance(m, ToolMessage)]
    tool_count = len(tool_msgs)
    reached = any(m.name in terminal_tools for m in tool_msgs)
    # Rejected tool calls are wasted turns, and they were invisible here: a run
    # where 29% of calls failed schema validation looked identical to a clean one.
    # Every prefix ToolNode uses for a call it could not complete: schema
    # validation ("Error invoking"), a raising handler ("Error executing"), an
    # unknown tool name, and the generic template ("Error: ...").
    # `_text_of` rather than `str(...)`: some LC versions wrap tool content in
    # blocks, and `str([{'type': 'text', ...}])` never matches a prefix, so the
    # rejected calls would stay invisible on exactly those providers.
    failed = [m for m in tool_msgs
              if _text_of(m).startswith(("Error invoking tool",
                                         "Error executing tool", "Error:"))]
    failed_names = sorted({m.name or "?" for m in failed})

    if emit is None:
        status = (GREEN("reached terminal tool") if reached
                  else YELLOW("NO terminal tool — run TRUNCATED, no recommendation"))
        fail_note = ""
        if failed:
            fail_note = YELLOW(f" · {len(failed)} REJECTED tool calls ({', '.join(failed_names)})")
        print(f"  {DIM('─' * 60)}", flush=True)
        print(f"  {DIM(f'{tool_count} tool calls · {elapsed:.0f}s · ')}{status}{fail_note}\n",
              flush=True)
    else:
        emit({
            "kind": "summary",
            "tool_count": tool_count,
            "elapsed": elapsed,
            "reached_terminal": reached,
            "failed_count": len(failed),
            "failed_names": failed_names,
        })
    return final_state
