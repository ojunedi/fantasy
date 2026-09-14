"""
Opponent defense matchup tool — enhanced with DvP (defense vs. position) stats
and team offense context.

For each rostered player shows:
  1. Opponent defense (DvP) — how that defense performs against the player's
     position, with position-specific per-game stats and a favorability rank.
  2. Player's own team offense — passing or rushing context depending on position.

Data sources:
  - nflreadpy  → per-player game logs for DvP computation
  - ESPN public APIs (no auth) → scoreboard, team list, team season stats
"""
from __future__ import annotations

from typing import Any

import httpx
import nflreadpy as nfl
import polars as pl

# ---------------------------------------------------------------------------
# ESPN API URLs
# ---------------------------------------------------------------------------

ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
ESPN_TEAMS_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams"

# ---------------------------------------------------------------------------
# ESPN abbreviation → nflverse abbreviation mapping
# ---------------------------------------------------------------------------

ESPN_TO_NFLVERSE: dict[str, str] = {
    "LAR": "LA",   # Rams
    "WSH": "WAS",  # Washington Commanders (ESPN uses both)
    "LVR": "LV",   # Raiders (ESPN sometimes uses LVR)
}

# ---------------------------------------------------------------------------
# Module-level caches
# ---------------------------------------------------------------------------

# Maps requested season → (DataFrame, actual_season_used)
_STATS_CACHE: dict[int, tuple[Any, int]] = {}

# Maps ESPN proTeamId → flat stats dict
_TEAM_STATS_CACHE: dict[str, dict[str, float]] = {}

# ---------------------------------------------------------------------------
# Helper: DvP favorability label
# ---------------------------------------------------------------------------

def _rank_label(rank: int) -> str:
    """Return a human-readable label for a 1-32 fantasy favorability rank."""
    if rank <= 8:
        return "FAVORABLE"
    elif rank <= 16:
        return "NEUTRAL"
    elif rank <= 24:
        return "TOUGH"
    else:
        return "VERY TOUGH"


# ---------------------------------------------------------------------------
# nflreadpy data loading with season fallback
# ---------------------------------------------------------------------------

def _load_player_stats(season: int) -> tuple[pl.DataFrame, int]:
    """Load player stats from nflreadpy for *season*, falling back to season-1
    when fewer than 4 regular-season weeks are available.

    Returns (DataFrame, actual_season_used).
    """
    if season in _STATS_CACHE:
        return _STATS_CACHE[season]

    def _try(s: int) -> pl.DataFrame:
        df = nfl.load_player_stats(seasons=[s])
        if not isinstance(df, pl.DataFrame):
            try:
                df = pl.from_pandas(df)  # type: ignore[attr-defined]
            except Exception:
                df = pl.DataFrame()
        return df

    df = _try(season)
    try:
        reg_weeks = df.filter(pl.col("season_type") == "REG")["week"].n_unique()
    except Exception:
        reg_weeks = 0

    if reg_weeks >= 4:
        result: tuple[pl.DataFrame, int] = (df, season)
        _STATS_CACHE[season] = result
        return result

    # Fallback to previous season
    fallback = season - 1
    if fallback in _STATS_CACHE:
        _STATS_CACHE[season] = _STATS_CACHE[fallback]
        return _STATS_CACHE[season]

    df_fb = _try(fallback)
    result = (df_fb, fallback)
    _STATS_CACHE[season] = result
    _STATS_CACHE[fallback] = result
    return result


# ---------------------------------------------------------------------------
# DvP computation
# ---------------------------------------------------------------------------

def _compute_dvp(df: pl.DataFrame, pos: str) -> dict[str, dict]:
    """Compute defense-vs-position stats per team for *pos*.

    Returns {nflverse_team_abbr: stats_dict} where rank 1 = highest fantasy
    points allowed = most favorable matchup for the offensive player.
    """
    if pos not in ("QB", "RB", "WR", "TE"):
        return {}

    try:
        base = df.filter(
            (pl.col("season_type") == "REG") & (pl.col("position") == pos)
        )
        if base.is_empty():
            return {}
    except Exception:
        return {}

    try:
        if pos in ("WR", "TE"):
            per_week = base.group_by(["opponent_team", "week"]).agg([
                pl.col("fantasy_points_ppr").sum().alias("fp"),
                pl.col("targets").sum().alias("targets"),
                pl.col("receiving_yards").sum().alias("rec_yards"),
                pl.col("receiving_tds").sum().alias("rec_tds"),
                pl.col("receiving_air_yards").sum().alias("air_yards"),
            ])
            per_team = per_week.group_by("opponent_team").agg([
                pl.col("fp").mean().alias("fp_pg"),
                pl.len().alias("games"),
                pl.col("targets").mean().alias("targets_pg"),
                pl.col("rec_yards").mean().alias("rec_yards_pg"),
                pl.col("rec_tds").mean().alias("rec_tds_pg"),
                pl.col("air_yards").mean().alias("air_yards_pg"),
            ])
        elif pos == "QB":
            per_week = base.group_by(["opponent_team", "week"]).agg([
                pl.col("fantasy_points_ppr").sum().alias("fp"),
                pl.col("passing_yards").sum().alias("pass_yards"),
                pl.col("passing_tds").sum().alias("pass_tds"),
                pl.col("sacks").sum().alias("sacks"),
            ])
            per_team = per_week.group_by("opponent_team").agg([
                pl.col("fp").mean().alias("fp_pg"),
                pl.len().alias("games"),
                pl.col("pass_yards").mean().alias("pass_yards_pg"),
                pl.col("pass_tds").mean().alias("pass_tds_pg"),
                pl.col("sacks").mean().alias("sacks_pg"),
            ])
        else:  # RB
            per_week = base.group_by(["opponent_team", "week"]).agg([
                pl.col("fantasy_points_ppr").sum().alias("fp"),
                pl.col("carries").sum().alias("carries"),
                pl.col("rushing_yards").sum().alias("rush_yds"),
                pl.col("rushing_tds").sum().alias("rush_tds"),
                pl.col("targets").sum().alias("targets"),
                pl.col("receiving_yards").sum().alias("rec_yds"),
            ])
            per_team = per_week.group_by("opponent_team").agg([
                pl.col("fp").mean().alias("fp_pg"),
                pl.len().alias("games"),
                pl.col("carries").mean().alias("carries_pg"),
                pl.col("rush_yds").mean().alias("rush_yds_pg"),
                pl.col("rush_tds").mean().alias("rush_tds_pg"),
                pl.col("targets").mean().alias("targets_pg"),
                pl.col("rec_yds").mean().alias("rec_yds_pg"),
            ])
    except Exception:
        return {}

    # Rank 1 = highest fp_pg = most fantasy points allowed = most favorable
    try:
        ranked = per_team.with_columns(
            pl.col("fp_pg").rank(method="min", descending=True).alias("rank")
        )
        total = ranked.height
    except Exception:
        ranked = per_team.with_columns(pl.lit(0).cast(pl.Int64).alias("rank"))
        total = ranked.height

    result: dict[str, dict] = {}
    for row in ranked.iter_rows(named=True):
        team = row["opponent_team"]
        result[team] = {**row, "total": total}

    return result


def _format_dvp_section(
    dvp: dict, pos: str, opp_abbr: str, actual_season: int
) -> list[str]:
    """Format a DvP block into display lines."""
    games = int(dvp.get("games", 0))
    rank = int(dvp.get("rank", 0))
    total = int(dvp.get("total", 32))
    fp_pg = float(dvp.get("fp_pg", 0.0))
    label = _rank_label(rank) if rank > 0 else "?"

    lines = [
        f"  {opp_abbr} Defense vs {pos} ({actual_season} reg season, {games} games):",
        f"    Fantasy pts allowed/g: {fp_pg:.1f}  [rank {rank}/{total} — {label}]",
    ]

    if pos in ("WR", "TE"):
        lines += [
            f"    Targets allowed/g:     {dvp.get('targets_pg', 0.0):.1f}",
            f"    Rec yards allowed/g:   {dvp.get('rec_yards_pg', 0.0):.1f}",
            f"    Rec TDs/g:             {dvp.get('rec_tds_pg', 0.0):.2f}",
            f"    Air yards allowed/g:   {dvp.get('air_yards_pg', 0.0):.1f}",
        ]
    elif pos == "QB":
        lines += [
            f"    Pass yards allowed/g:  {dvp.get('pass_yards_pg', 0.0):.1f}",
            f"    Pass TDs allowed/g:    {dvp.get('pass_tds_pg', 0.0):.2f}",
            f"    Sacks/g:               {dvp.get('sacks_pg', 0.0):.1f}",
        ]
    elif pos == "RB":
        lines += [
            f"    Carries allowed/g:     {dvp.get('carries_pg', 0.0):.1f}",
            f"    Rush yards allowed/g:  {dvp.get('rush_yds_pg', 0.0):.1f}",
            f"    Rush TDs/g:            {dvp.get('rush_tds_pg', 0.0):.2f}",
            f"    Targets allowed/g:     {dvp.get('targets_pg', 0.0):.1f}",
            f"    Rec yards allowed/g:   {dvp.get('rec_yds_pg', 0.0):.1f}",
        ]

    return lines


# ---------------------------------------------------------------------------
# ESPN team offense stats
# ---------------------------------------------------------------------------

def _fetch_team_offense(team_id: str) -> dict[str, float]:
    """Fetch ESPN team season stats.

    Returns a flat {key: value} dict where keys are "{category}.{stat_name}"
    and also "{stat_name}" for convenience.  Returns {} on any error.
    """
    if team_id in _TEAM_STATS_CACHE:
        return _TEAM_STATS_CACHE[team_id]

    url = (
        f"https://site.api.espn.com/apis/site/v2/sports/football/"
        f"nfl/teams/{team_id}/statistics"
    )
    try:
        resp = httpx.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        categories = data["results"]["stats"]["categories"]
    except Exception:
        _TEAM_STATS_CACHE[team_id] = {}
        return {}

    stats: dict[str, float] = {}
    for cat in categories:
        cat_name = cat.get("name", "")
        for stat in cat.get("stats", []):
            sname = stat.get("name", "")
            raw = stat.get("value", stat.get("perGameValue", 0.0))
            try:
                sval = float(raw) if raw is not None else 0.0
            except (TypeError, ValueError):
                sval = 0.0
            stats[f"{cat_name}.{sname}"] = sval
            stats[sname] = sval  # flat access; last category wins on collision

    _TEAM_STATS_CACHE[team_id] = stats
    return stats


def _format_team_offense_section(
    team_stats: dict[str, float], pos: str, team_abbr: str, actual_season: int
) -> list[str]:
    """Format team offense block into display lines."""
    lines: list[str] = []

    def _get(*keys: str) -> float | None:
        for k in keys:
            v = team_stats.get(k)
            if v is not None:
                return v
        return None

    if pos in ("QB", "WR", "TE"):
        lines.append(f"  {team_abbr} Passing Offense ({actual_season} season stats):")

        pass_ypg = _get("passing.passingYardsPerGame", "passingYardsPerGame")
        lines.append(
            f"    Pass yards/g:    {pass_ypg:.1f}" if pass_ypg is not None
            else "    Pass yards/g:    (unavailable)"
        )

        pass_tds = _get("passing.passingTouchdowns", "passingTouchdowns")
        games = _get("gamesPlayed")
        if pass_tds is not None and games and games > 0:
            lines.append(f"    Pass TDs/g:      {pass_tds / games:.2f}")
        elif pass_tds is not None:
            lines.append(f"    Pass TDs total:  {pass_tds:.0f}")
        else:
            lines.append("    Pass TDs/g:      (unavailable)")

        ypa = _get("passing.yardsPerPassAttempt", "yardsPerPassAttempt")
        lines.append(
            f"    Yards/attempt:   {ypa:.1f}" if ypa is not None
            else "    Yards/attempt:   (unavailable)"
        )

    elif pos == "RB":
        lines.append(f"  {team_abbr} Rushing Offense ({actual_season} season stats):")

        rush_ypg = _get("rushing.rushingYardsPerGame", "rushingYardsPerGame")
        lines.append(
            f"    Rush yards/g:    {rush_ypg:.1f}" if rush_ypg is not None
            else "    Rush yards/g:    (unavailable)"
        )

        rush_tds = _get("rushing.rushingTouchdowns", "rushingTouchdowns")
        games = _get("gamesPlayed")
        if rush_tds is not None and games and games > 0:
            lines.append(f"    Rush TDs/g:      {rush_tds / games:.2f}")
        elif rush_tds is not None:
            lines.append(f"    Rush TDs total:  {rush_tds:.0f}")
        else:
            lines.append("    Rush TDs/g:      (unavailable)")

        ypc = _get("rushing.yardsPerRushAttempt", "yardsPerRushAttempt")
        lines.append(
            f"    Yards/carry:     {ypc:.1f}" if ypc is not None
            else "    Yards/carry:     (unavailable)"
        )

    return lines


# ---------------------------------------------------------------------------
# Existing ESPN helpers (teams map + scoreboard)
# ---------------------------------------------------------------------------

def _fetch_teams_map() -> dict[str, dict[str, str]]:
    """Return {team_id: {"abbr": "...", "name": "..."}} from the ESPN teams endpoint."""
    resp = httpx.get(ESPN_TEAMS_URL, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    result: dict[str, dict[str, str]] = {}
    try:
        for league in data["sports"][0]["leagues"]:
            for entry in league.get("teams", []):
                team = entry.get("team", {})
                tid = str(team.get("id", ""))
                if tid:
                    result[tid] = {
                        "abbr": team.get("abbreviation", tid),
                        "name": team.get("displayName", tid),
                    }
    except (KeyError, IndexError, TypeError):
        pass
    return result


def _fetch_scoreboard(week: int, season: int) -> list[dict]:
    """Return parsed game list from the ESPN NFL scoreboard."""
    params = {"week": week, "seasontype": 2, "dates": season}
    resp = httpx.get(ESPN_SCOREBOARD_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    games: list[dict] = []
    for event in data.get("events", []):
        for competition in event.get("competitions", []):
            game: dict[str, str] = {}
            for comp in competition.get("competitors", []):
                team = comp.get("team", {})
                side = comp.get("homeAway", "home")
                tid = str(team.get("id", ""))
                abbr = team.get("abbreviation", tid)
                game[f"{side}_id"] = tid
                game[f"{side}_abbr"] = abbr
            game["date"] = competition.get("date", "")
            if "home_id" in game and "away_id" in game:
                games.append(game)
    return games


def _build_opponent_map(games: list[dict]) -> dict[str, dict[str, str]]:
    """Return {team_id: {"opponent_abbr": ..., "home_away": ..., "opponent_id": ...}}."""
    result: dict[str, dict[str, str]] = {}
    for game in games:
        home_id = game.get("home_id", "")
        away_id = game.get("away_id", "")
        home_abbr = game.get("home_abbr", home_id)
        away_abbr = game.get("away_abbr", away_id)
        if home_id:
            result[home_id] = {
                "opponent_abbr": away_abbr,
                "opponent_id": away_id,
                "home_away": "home",
            }
        if away_id:
            result[away_id] = {
                "opponent_abbr": home_abbr,
                "opponent_id": home_id,
                "home_away": "away",
            }
    return result


# ---------------------------------------------------------------------------
# Main tool function
# ---------------------------------------------------------------------------

def tool_get_opponent_defense(ctx: Any, detail: bool = False) -> str:
    """
    For each player on my roster, shows the opponent defense-vs-position matchup.

    Compact by default — one line per player with the fantasy-points-allowed rate
    and rank, which is the part decisions actually turn on. The full per-stat
    breakdown plus the player's own team-offense context runs ~11 lines per
    player, which is a large, permanent cost in the agent's message history, so
    it is opt-in via detail=True.

    Uses ESPN public APIs (no auth) and nflreadpy for historical player stats.
    """
    # ---- Collect roster ----
    try:
        roster = ctx.roster()
        players = roster.players
    except Exception as exc:
        return f"Error fetching roster: {exc}"

    week: int = ctx.week
    season: int = ctx.season

    # ---- ESPN teams map ----
    teams_map: dict[str, dict[str, str]] = {}
    teams_error: str | None = None
    try:
        teams_map = _fetch_teams_map()
    except Exception as exc:
        teams_error = f"(teams lookup failed: {exc})"

    # ---- Scoreboard ----
    games: list[dict] = []
    scoreboard_error: str | None = None
    try:
        games = _fetch_scoreboard(week, season)
    except Exception as exc:
        scoreboard_error = f"(scoreboard unavailable: {exc})"

    opponent_map = _build_opponent_map(games)

    # ---- nflreadpy stats (once, cached) ----
    stats_df: pl.DataFrame | None = None
    actual_stats_season: int = season
    stats_error: str | None = None
    try:
        stats_df, actual_stats_season = _load_player_stats(season)
    except Exception as exc:
        stats_error = f"(nflreadpy unavailable: {exc})"

    # ---- DvP per position (lazy) ----
    dvp_by_pos: dict[str, dict[str, dict]] = {}

    def _get_dvp(pos: str) -> dict[str, dict]:
        if stats_df is None:
            return {}
        if pos not in dvp_by_pos:
            dvp_by_pos[pos] = _compute_dvp(stats_df, pos)
        return dvp_by_pos[pos]

    # ---- Build output ----
    header = f"Opponent defense matchup — Week {week}, {season} season:"
    if not detail:
        header += ("\n  (fantasy points allowed per game to the position; "
                   "rank 1 = most generous. Call with detail=true for per-stat "
                   "breakdowns and team-offense context.)")
    lines: list[str] = [header]
    if teams_error:
        lines.append(f"  WARNING: {teams_error}")
    if scoreboard_error:
        lines.append(f"  WARNING: {scoreboard_error}")
    if stats_error:
        lines.append(f"  WARNING: {stats_error}")

    for rp in players:
        player = rp.player
        tag = "STARTER" if rp.is_starter else "bench"
        pos = player.position.value
        pro_team_id: str | None = player.nfl_team

        # ---- Players with no NFL team ----
        if not pro_team_id:
            lines.append(
                f"  {player.name} ({pos}) [{tag}] | NFL team: unknown"
            )
            continue

        # ---- Resolve team abbreviation ----
        team_info = teams_map.get(pro_team_id, {})
        team_abbr = team_info.get("abbr", pro_team_id)

        # ---- Resolve opponent ----
        opp_info = opponent_map.get(pro_team_id)

        if not opp_info:
            lines.append(
                f"  {player.name} ({pos}) [{tag}]"
                f" | {team_abbr}"
                f" | BYE or not scheduled (Week {week})"
            )
            continue

        opp_abbr = opp_info["opponent_abbr"]
        home_away = opp_info["home_away"]
        vs_str = f"vs {opp_abbr}" if home_away == "home" else f"@ {opp_abbr}"

        # ---- Resolve DvP once; both layouts need it ----
        dvp = None
        if pos not in ("K", "DST"):
            nfl_opp_abbr = ESPN_TO_NFLVERSE.get(opp_abbr, opp_abbr)
            dvp = _get_dvp(pos).get(nfl_opp_abbr)

        # ---- Compact layout: one line per player ----
        if not detail:
            stem = f"  {player.name} ({pos}) [{tag}] {team_abbr} {vs_str}"
            if pos in ("K", "DST"):
                lines.append(stem)
            elif dvp:
                rank = int(dvp.get("rank", 0))
                total = int(dvp.get("total", 32))
                label = _rank_label(rank) if rank > 0 else "?"
                lines.append(f"{stem} — {opp_abbr} allows {float(dvp.get('fp_pg', 0.0)):.1f} "
                             f"fp/g to {pos} [{rank}/{total} {label}]")
            else:
                lines.append(f"{stem} — no DvP data for {opp_abbr} vs {pos}")
            continue

        # ---- Detailed layout ----
        lines.append(f"\n=== {player.name} ({pos}) [{tag}] | {team_abbr} {vs_str} ===")
        if pos in ("K", "DST"):
            lines.append(f"  (DvP not shown for {pos})")
            continue

        if dvp:
            lines.append("")
            lines.extend(_format_dvp_section(dvp, pos, opp_abbr, actual_stats_season))
        else:
            lines.append(f"  (DvP data unavailable for {opp_abbr} vs {pos})")

        try:
            team_stats = _fetch_team_offense(pro_team_id)
        except Exception:
            team_stats = {}

        offense_lines = _format_team_offense_section(
            team_stats, pos, team_abbr, actual_stats_season
        )
        if offense_lines:
            lines.append("")
            lines.extend(offense_lines)

    if len(lines) == 1:
        lines.append("  (no players on roster)")

    return "\n".join(lines)
