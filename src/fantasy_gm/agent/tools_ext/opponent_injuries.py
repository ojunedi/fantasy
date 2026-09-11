"""
Tool: get_opponent_injuries

For each player on my roster (starters prioritized), shows the key injuries
on their NFL opponent's team this week.

Uses ESPN's public (no-auth) sports APIs:
  - site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard
  - site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{abbr}/injuries
"""
from __future__ import annotations

from typing import Any

import httpx

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
INJURY_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{abbr}/injuries"

# Injury statuses worth surfacing to the GM
SIGNIFICANT_STATUSES = {"Out", "Doubtful", "Questionable"}


def _fetch_scoreboard_matchups(week: int, season: int) -> dict[str, dict[str, str]]:
    """Fetch the NFL scoreboard and return a matchup lookup.

    Returns {team_id: {"abbr": "...", "opponent_abbr": "..."}} for every team
    that has a game this week.  Teams on bye are absent.
    """
    resp = httpx.get(
        SCOREBOARD_URL,
        params={"week": week, "seasontype": 2, "dates": season},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    result: dict[str, dict[str, str]] = {}
    for event in data.get("events", []):
        for competition in event.get("competitions", []):
            competitors = competition.get("competitors", [])
            if len(competitors) != 2:
                continue
            t0 = competitors[0].get("team", {})
            t1 = competitors[1].get("team", {})
            id0 = str(t0.get("id", ""))
            id1 = str(t1.get("id", ""))
            abbr0 = t0.get("abbreviation", id0)
            abbr1 = t1.get("abbreviation", id1)
            if id0:
                result[id0] = {"abbr": abbr0, "opponent_abbr": abbr1}
            if id1:
                result[id1] = {"abbr": abbr1, "opponent_abbr": abbr0}
    return result


def _fetch_team_injuries(abbr: str) -> list[dict[str, str]] | None:
    """Fetch significant injuries for an NFL team.

    Returns a list of injury dicts on success, None on connection/server error,
    and an empty list if the endpoint returns 404 (unknown slug).

    Each dict has keys: name, position, status, injury.
    """
    slug = abbr.lower()
    url = INJURY_URL.format(abbr=slug)
    try:
        resp = httpx.get(url, timeout=15)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    injuries: list[dict[str, str]] = []
    for item in data.get("injuries", []):
        status = item.get("status", "")
        if status not in SIGNIFICANT_STATUSES:
            continue
        athlete = item.get("athlete", {})
        inj_type = item.get("type", {}).get("description", "Unknown")
        injuries.append(
            {
                "name": athlete.get("displayName", "Unknown"),
                "position": athlete.get("position", {}).get("abbreviation", "?"),
                "status": status,
                "injury": inj_type,
            }
        )
    return injuries


def tool_get_opponent_injuries(ctx: Any) -> str:
    """
    For each player on my roster (starters prioritized), shows the key injuries
    on their NFL opponent's team this week.

    Focus: players listed as Out, Doubtful, or Questionable on the opposing team.
    This helps spot:
    - My WR's coverage matchup improving if opposing CB1 is out
    - My QB's game script changing if opposing pass rush is hobbled
    - My RB facing a weakened or strengthened run defense

    Uses ESPN public team-injury API (no auth needed):
    GET https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_slug}/injuries

    Also uses the scoreboard to determine opponent team:
    GET https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard
    params: week={week}, seasontype=2, dates={season}

    Player's NFL team is in player.nfl_team (set from proTeamId by the ESPN adapter).
    The ESPN sports API team slug is the lowercased abbreviation (e.g. "kc", "sf", "ne").
    """
    # 1. Get roster players, starters first
    try:
        roster = ctx.roster()
        players = sorted(roster.players, key=lambda rp: (0 if rp.is_starter else 1))
    except Exception as exc:
        return f"Error fetching roster: {exc}"

    week: int = ctx.week
    season: int = ctx.season

    # 2. Get scoreboard to build team_id → matchup info
    try:
        matchup_map = _fetch_scoreboard_matchups(week, season)
    except Exception as exc:
        return f"Error fetching NFL scoreboard: {exc}"

    # 3. Iterate players, fetch opponent injuries (cache by opponent abbr)
    injury_cache: dict[str, list[dict[str, str]] | None] = {}
    lines: list[str] = [f"Opponent injuries — Week {week}, {season} season:\n"]

    for rp in players:
        player = rp.player
        starter_tag = "STARTER" if rp.is_starter else "bench"
        pos = player.position.value
        name = player.name

        # nfl_team is the proTeamId as a string (e.g. "12" for KC)
        nfl_team_id = player.nfl_team
        if not nfl_team_id:
            lines.append(
                f"=== {name} ({pos}) [{starter_tag}] — NFL team unknown ==="
            )
            lines.append("")
            continue

        matchup = matchup_map.get(nfl_team_id)
        if not matchup:
            lines.append(
                f"=== {name} ({pos}) [{starter_tag}] plays for team {nfl_team_id}"
                f" — on BYE or not scheduled this week ==="
            )
            lines.append("")
            continue

        team_abbr = matchup["abbr"]
        opponent_abbr = matchup["opponent_abbr"]

        lines.append(
            f"=== Your player: {name} ({pos}) [{starter_tag}]"
            f" plays for {team_abbr} — {team_abbr} faces {opponent_abbr} ==="
        )

        # Fetch injuries for the opponent (de-duplicate calls)
        if opponent_abbr not in injury_cache:
            injury_cache[opponent_abbr] = _fetch_team_injuries(opponent_abbr)

        injuries = injury_cache[opponent_abbr]

        if injuries is None:
            lines.append(
                f"  [Could not retrieve injury data for {opponent_abbr} — API error]"
            )
        elif not injuries:
            lines.append(f"  No significant injuries reported for {opponent_abbr}.")
        else:
            lines.append(f"  Key {opponent_abbr} injuries:")
            for inj in injuries:
                lines.append(
                    f"    • {inj['name']} ({inj['position']})"
                    f" — {inj['status']} ({inj['injury']})"
                )
        lines.append("")

    return "\n".join(lines).rstrip()
