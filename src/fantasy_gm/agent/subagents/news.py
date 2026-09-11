"""
News-interpreter sub-agent (single-shot LLM).

Reads recent unstructured NFL news for a player — ESPN headlines, and optional
Tavily web results — and extracts structured, fantasy-relevant events:

    {"events": [{"type": "role_change|injury|trade|usage_trend|other",
                 "impact": "up|down|neutral", "summary": "<one sentence>"}],
     "net_outlook": "up|down|neutral",
     "note": "<one sentence>"}

Reuses `signals/news.py` for the raw feeds. Single model call; degrades to a
neutral result with a note when no LLM/API key is available.
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from fantasy_gm.agent.subagents.base import default_llm, parse_json_object, _message_text
from fantasy_gm.signals.news import get_nfl_news, tavily_available, web_search

_SYSTEM = """\
You extract fantasy-relevant signal from NFL news about a specific player. \
Given raw news text, output ONLY a JSON object:

{"events": [{"type": "role_change|injury|trade|usage_trend|other",
             "impact": "up|down|neutral", "summary": "<one sentence>"}],
 "net_outlook": "up|down|neutral",
 "note": "<one sentence overall read>"}

- Only include events actually supported by the text. If nothing relevant, \
return an empty events list and net_outlook "neutral".
- "up" = the player's fantasy value/opportunity is rising; "down" = falling.
Output the JSON and nothing else."""


def interpret_news(
    player_name: str,
    use_web_search: bool = True,
    llm=None,
    news_text: str | None = None,
) -> dict:
    """Interpret recent news for a player into structured events.

    `news_text` can be injected for testing; otherwise it is gathered from ESPN
    (always) and Tavily (if a key is configured and use_web_search is True).
    """
    llm = llm if llm is not None else default_llm()
    neutral = {"events": [], "net_outlook": "neutral",
               "note": "News interpreter unavailable (no LLM configured)."}

    if news_text is None:
        chunks = [get_nfl_news(limit=15)]
        if use_web_search and tavily_available():
            chunks.append(web_search(f"{player_name} fantasy football news this week"))
        news_text = "\n\n".join(chunks)

    if llm is None:
        return neutral

    user = f"Player: {player_name}\n\nRecent news:\n{news_text}"
    try:
        resp = llm.invoke([SystemMessage(content=_SYSTEM), HumanMessage(content=user)])
    except Exception as e:
        return {**neutral, "note": f"News interpreter error: {e}"}

    parsed = parse_json_object(_message_text(resp))
    if parsed is None:
        return {**neutral, "note": "News interpreter returned no parseable JSON."}
    parsed.setdefault("events", [])
    parsed.setdefault("net_outlook", "neutral")
    parsed.setdefault("note", "")
    return parsed
