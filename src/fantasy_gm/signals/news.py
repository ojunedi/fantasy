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


# One read per feed per 15 minutes (NFR-03): the News page asks for the league
# feed and one feed per rostered team, and should not do that on every load.
NEWS_TTL_SECONDS = 15 * 60
_feed_cache: dict[str | None, tuple[float, list[dict]]] = {}


def fetch_articles(team_id: str | None = None, limit: int = 50) -> list[dict]:
    """ESPN news stories, normalised: id, headline, description, url, published,
    athlete_ids and team_ids from ESPN's own tags. `team_id` is ESPN's team id
    (the roster's proTeamId). Raises on a failed read."""
    params: dict = {"limit": limit}
    if team_id:
        params["team"] = team_id
    resp = httpx.get(ESPN_NEWS_URL, params=params, timeout=15)
    resp.raise_for_status()
    out = []
    for a in resp.json().get("articles", []):
        headline = (a.get("headline") or "").strip()
        url = ((a.get("links") or {}).get("web") or {}).get("href")
        if not headline or not url:
            continue  # a story we cannot link to or name is not shown
        cats = a.get("categories") or []
        out.append({
            "id": str(a.get("id") or url),
            "headline": headline,
            "description": (a.get("description") or "").strip(),
            "url": url,
            "published": a.get("published"),
            "athlete_ids": [str(c.get("athleteId") or (c.get("athlete") or {}).get("id"))
                            for c in cats if c.get("type") == "athlete"
                            and (c.get("athleteId") or (c.get("athlete") or {}).get("id"))],
            "team_ids": [str(c.get("teamId") or (c.get("team") or {}).get("id"))
                         for c in cats if c.get("type") == "team"
                         and (c.get("teamId") or (c.get("team") or {}).get("id"))],
        })
    return out


def cached_articles(team_id: str | None = None, now: float | None = None) -> list[dict]:
    """`fetch_articles`, memoised per feed for NEWS_TTL_SECONDS."""
    import time
    now = now if now is not None else time.time()
    hit = _feed_cache.get(team_id)
    if hit and now - hit[0] < NEWS_TTL_SECONDS:
        return hit[1]
    articles = fetch_articles(team_id)
    _feed_cache[team_id] = (now, articles)
    return articles


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
