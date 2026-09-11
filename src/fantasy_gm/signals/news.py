"""
Sports news + web search signal sources.

Two providers:
  - ESPN NFL news API: keyless, works immediately. Recent league-wide headlines
    and injury/roster notes. The "nice sports API".
  - Tavily web search: general-purpose, targeted research (e.g. a specific
    player's Week N injury status). Activates when TAVILY_API_KEY is set;
    degrades gracefully otherwise, consistent with the signal-availability design.

Both return plain text suitable for a tool result the agent reads.
"""
from __future__ import annotations

import os

import httpx

ESPN_NEWS_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/news"


def get_nfl_news(limit: int = 10) -> str:
    """Fetch recent NFL news headlines from ESPN's public news API (no key)."""
    try:
        resp = httpx.get(ESPN_NEWS_URL, params={"limit": limit}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return f"ESPN news unavailable: {e}"

    articles = data.get("articles", [])
    if not articles:
        return "No recent NFL news returned."

    lines = ["Recent NFL news (ESPN):"]
    for a in articles[:limit]:
        headline = a.get("headline", "").strip()
        desc = (a.get("description") or "").strip()
        published = (a.get("published") or "")[:10]
        lines.append(f"  [{published}] {headline}")
        if desc:
            lines.append(f"      {desc}")
    return "\n".join(lines)


def web_search(query: str, max_results: int = 5) -> str:
    """Run a general web search via Tavily. Returns a clear notice if no key."""
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return ("Web search unavailable: TAVILY_API_KEY is not set. "
                "Rely on ESPN news and projections, and factor this gap into your "
                "confidence (or abstain if the missing research is decisive).")
    try:
        from langchain_tavily import TavilySearch
        tool = TavilySearch(max_results=max_results, topic="news")
        result = tool.invoke({"query": query})
    except Exception as e:
        return f"Web search error: {e}"

    # TavilySearch returns a dict with a 'results' list
    if isinstance(result, dict):
        results = result.get("results", [])
        if not results:
            return f"No web results for: {query}"
        lines = [f"Web search results for '{query}':"]
        for r in results[:max_results]:
            title = r.get("title", "")
            content = (r.get("content") or "")[:300]
            url = r.get("url", "")
            lines.append(f"  - {title}\n    {content}\n    ({url})")
        return "\n".join(lines)
    return str(result)


def tavily_available() -> bool:
    return bool(os.environ.get("TAVILY_API_KEY", ""))
