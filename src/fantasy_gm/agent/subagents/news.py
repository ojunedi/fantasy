"""
News-interpreter sub-agent (single-shot LLM).

Reads recent unstructured NFL news — ESPN headlines, and optional Tavily web
results — and extracts structured, fantasy-relevant events per player:

    {"events": [{"type": "role_change|injury|trade|usage_trend|other",
                 "impact": "up|down|neutral", "summary": "<one sentence>"}],
     "net_outlook": "up|down|neutral",
     "note": "<one sentence>"}

`interpret_news_batch` is the primary entry point and interprets MANY players in
one model call. That is not just a cost win: the ESPN feed is league-wide and
identical for every player, so the per-player version re-sent the same corpus
once per name. Batching also lets the model see cross-player context — a backup
rising *because* of the starter's injury in the same feed — which N independent
single-player calls structurally cannot notice.

Reuses `signals/news.py` for the raw feeds. Degrades to neutral results with a
note when no LLM/API key is available.
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from fantasy_gm.agent.subagents.base import default_llm, parse_json_object, _message_text
from fantasy_gm.signals.news import get_nfl_news, tavily_available, web_search

# Players per model call. One call for a whole roster invites truncated or
# sloppy JSON, so chunk beyond this and keep the per-player token share sane.
_BATCH_SIZE = 8

_SYSTEM = """\
You extract fantasy-relevant signal from NFL news about specific players. \
Given raw news text and a list of players, output ONLY a JSON object keyed by \
the EXACT player names you were given:

{"players": {"<player name>": {"events": [{"type": "role_change|injury|trade|usage_trend|other",
                                           "impact": "up|down|neutral",
                                           "summary": "<one sentence>"}],
                               "net_outlook": "up|down|neutral",
                               "note": "<one sentence overall read>"}}}

- Include an entry for EVERY player listed, even if the news says nothing about \
them — in that case use an empty events list and net_outlook "neutral".
- Only include events actually supported by the text. Do not invent news.
- "up" = the player's fantasy value/opportunity is rising; "down" = falling.
- The news is league-wide: if an item about one player changes another listed \
player's outlook (a starter's injury lifting his backup), reflect that.
Output the JSON and nothing else."""

_NEUTRAL_NOTE = "News interpreter unavailable (no LLM configured)."


def _neutral(note: str = _NEUTRAL_NOTE) -> dict:
    return {"events": [], "net_outlook": "neutral", "note": note}


def _normalize(entry: object, fallback_note: str) -> dict:
    """Coerce one player's parsed entry into the documented shape."""
    if not isinstance(entry, dict):
        return _neutral(fallback_note)
    events = entry.get("events")
    return {
        "events": events if isinstance(events, list) else [],
        "net_outlook": entry.get("net_outlook") or "neutral",
        "note": entry.get("note") or "",
    }


def _gather_news_text(player_names: list[str], use_web_search: bool) -> str:
    """Fetch the shared league feed once, plus per-player web search if enabled."""
    chunks = [get_nfl_news(limit=15)]
    if use_web_search and tavily_available():
        for name in player_names:
            chunks.append(web_search(f"{name} fantasy football news this week"))
    return "\n\n".join(chunks)


def interpret_news_batch(
    player_names: list[str],
    use_web_search: bool = True,
    llm=None,
    news_text: str | None = None,
) -> dict[str, dict]:
    """Interpret recent news for many players in one model call per chunk.

    Returns a dict keyed by the player names as passed in. Players the model
    omits or mangles degrade to a neutral entry individually — one bad key does
    not poison the rest of the batch.
    """
    names = [n for n in dict.fromkeys(player_names) if n]
    if not names:
        return {}

    llm = llm if llm is not None else default_llm()
    if llm is None:
        return {name: _neutral() for name in names}

    if news_text is None:
        news_text = _gather_news_text(names, use_web_search)

    out: dict[str, dict] = {}
    for start in range(0, len(names), _BATCH_SIZE):
        out.update(_interpret_chunk(names[start:start + _BATCH_SIZE], news_text, llm))
    return out


def _interpret_chunk(names: list[str], news_text: str, llm) -> dict[str, dict]:
    roster = "\n".join(f"- {name}" for name in names)
    user = f"Players:\n{roster}\n\nRecent news:\n{news_text}"
    try:
        resp = llm.invoke([SystemMessage(content=_SYSTEM), HumanMessage(content=user)])
    except Exception as e:
        return {name: _neutral(f"News interpreter error: {e}") for name in names}

    parsed = parse_json_object(_message_text(resp))
    if not isinstance(parsed, dict):
        return {name: _neutral("News interpreter returned no parseable JSON.")
                for name in names}

    players = parsed.get("players")
    if not isinstance(players, dict):
        # A single-player response often comes back as the bare entry itself
        # rather than a name-keyed map; accept that when it is unambiguous.
        if len(names) == 1 and ("events" in parsed or "net_outlook" in parsed):
            return {names[0]: _normalize(parsed, "")}
        # Otherwise tolerate the mapping returned without the wrapper key.
        players = parsed
    # Match case-insensitively so a re-capitalized key still lands.
    by_lower = {str(k).strip().lower(): v for k, v in players.items()}
    return {
        name: _normalize(by_lower.get(name.strip().lower()),
                         "No entry returned for this player.")
        for name in names
    }


def interpret_news(
    player_name: str,
    use_web_search: bool = True,
    llm=None,
    news_text: str | None = None,
) -> dict:
    """Single-player convenience wrapper over `interpret_news_batch`."""
    result = interpret_news_batch([player_name], use_web_search=use_web_search,
                                  llm=llm, news_text=news_text)
    return result.get(player_name, _neutral())
