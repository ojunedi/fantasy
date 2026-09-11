"""
Signal collector — gathers all available signals into a SignalBundle.

Wired sources:
  - projections: ESPN's own weekly projections (scored under league rules)
  - injuries:    ESPN player injury status
  - usage:       nflverse volume trends (targets/carries/shares) per player
  - vegas:       implied team totals + game script from nflverse schedule lines
  - weather:     Open-Meteo forecast per stadium (dome-aware)

The nflverse-backed enrichment is best-effort and fully guarded: any failure
(offline, unmapped players, no schedule) degrades each source to available=False
rather than raising, consistent with the signal-availability design. It is also
skipped entirely when the roster carries no NFL-team info, keeping offline/unit
runs fast.
"""
from __future__ import annotations

from datetime import datetime

from fantasy_gm.adapters.espn import ESPNAdapter
from fantasy_gm.models import (
    InjuryReport,
    PlayerProjection,
    Position,
    UsageTrend,
    VegasLine,
)
from fantasy_gm.signals.base import SignalAvailability, SignalBundle

# ESPN proTeamId -> nflverse team abbreviation.
ESPN_PRO_TEAM_ABBR: dict[str, str] = {
    "1": "ATL", "2": "BUF", "3": "CHI", "4": "CIN", "5": "CLE", "6": "DAL",
    "7": "DEN", "8": "DET", "9": "GB", "10": "TEN", "11": "IND", "12": "KC",
    "13": "LV", "14": "LAR", "15": "MIA", "16": "MIN", "17": "NE", "18": "NO",
    "19": "NYG", "20": "NYJ", "21": "PHI", "22": "ARI", "23": "PIT", "24": "LAC",
    "25": "SF", "26": "SEA", "27": "TB", "28": "WAS", "29": "CAR", "30": "JAX",
    "33": "BAL", "34": "HOU",
}


def collect_signals(
    adapter: ESPNAdapter,
    week: int,
    season: int,
    roster_players: list,  # list[RosterPlayer]
    use_nflverse: bool = True,
) -> SignalBundle:
    bundle = SignalBundle(week=week, season=season)

    # --- Projections (ESPN, real) ---
    try:
        raw_proj = adapter.get_projections(week=week, season=season)
        cached_at = adapter._cache.get_cached_at(
            f"{season}_{adapter.league_id}_"
            + str(sorted({"view": "kona_player_info", "scoringPeriodId": week}.items()))
        )
        as_of = datetime.utcfromtimestamp(cached_at) if cached_at else datetime.utcnow()
        for rp in roster_players:
            pid = rp.player.platform_id
            if pid in raw_proj:
                bundle.projections[pid] = PlayerProjection(
                    player_id=pid,
                    player_name=rp.player.name,
                    projected_points=raw_proj[pid],
                    position=rp.player.position,
                    nfl_team=rp.player.nfl_team,
                    week=week,
                    season=season,
                )
        bundle.availability.append(SignalAvailability(
            name="projections",
            available=len(bundle.projections) > 0,
            as_of=as_of,
            source="ESPN",
            note=f"{len(bundle.projections)}/{len(roster_players)} rostered players projected",
        ))
    except Exception as e:
        bundle.availability.append(SignalAvailability(
            name="projections", available=False, source="ESPN", note=f"error: {e}"
        ))

    # --- Injuries (ESPN status, real) ---
    injured = 0
    for rp in roster_players:
        status = rp.player.status
        bundle.injuries[rp.player.platform_id] = InjuryReport(
            player_id=rp.player.platform_id,
            player_name=rp.player.name,
            status=status,
            week=week,
        )
        if status.value not in ("ACTIVE",):
            injured += 1
    bundle.availability.append(SignalAvailability(
        name="injuries",
        available=True,
        as_of=datetime.utcnow(),
        source="ESPN",
        note=f"{injured} players not fully active",
    ))

    # --- nflverse-backed usage / vegas / weather (best-effort) ---
    team_abbrevs = {
        ESPN_PRO_TEAM_ABBR.get(str(rp.player.nfl_team))
        for rp in roster_players if rp.player.nfl_team
    }
    team_abbrevs.discard(None)
    if use_nflverse and team_abbrevs:
        _enrich_from_nflverse(bundle, roster_players, week, season)
    else:
        for name in ("usage_trends", "weather", "vegas_lines"):
            bundle.availability.append(SignalAvailability(
                name=name, available=False, source="nflverse/open-meteo",
                note="skipped — roster carries no NFL-team info",
            ))

    return bundle


def _enrich_from_nflverse(
    bundle: SignalBundle,
    roster_players: list,
    week: int,
    season: int,
) -> None:
    """Populate usage / vegas / weather from nflverse + Open-Meteo. Never raises."""
    from fantasy_gm.core.usage import usage_summary
    from fantasy_gm.signals.sources import nflverse as nv

    # -- Usage trends --
    try:
        id_map = nv.build_id_map()
        rows = nv.player_stat_rows(season, through_week=week - 1)
        by_gsis: dict[str, list[dict]] = {}
        for r in rows:
            by_gsis.setdefault(r["player_id"], []).append(r)
        n_usage = 0
        for rp in roster_players:
            gsis = id_map.gsis(rp.player.platform_id)
            player_rows = by_gsis.get(gsis or "", [])
            if not player_rows:
                continue
            prof = usage_summary(player_rows, player_id=rp.player.platform_id)
            w3 = prof.window(3)
            if w3 is None:
                continue
            bundle.usage[rp.player.platform_id] = UsageTrend(
                player_id=rp.player.platform_id,
                player_name=rp.player.name,
                position=rp.player.position,
                nfl_team=ESPN_PRO_TEAM_ABBR.get(str(rp.player.nfl_team), "") or "",
                targets_last3=w3.targets,
                carries_last3=w3.carries,
                snap_share_last3=w3.snap_share or None,
                weeks_sampled=w3.games,
            )
            n_usage += 1
        bundle.availability.append(SignalAvailability(
            name="usage_trends", available=n_usage > 0, as_of=datetime.utcnow(),
            source="nflverse", note=f"{n_usage} players with usage history",
        ))
    except Exception as e:
        bundle.availability.append(SignalAvailability(
            name="usage_trends", available=False, source="nflverse", note=f"error: {e}"
        ))

    # -- Vegas lines (implied totals) from schedule --
    try:
        from fantasy_gm.core.game_env import from_schedule_row
        sched = [r for r in nv.schedule_rows(season) if r.get("week") == week]
        team_env: dict[str, VegasLine] = {}
        for rp in roster_players:
            abbr = ESPN_PRO_TEAM_ABBR.get(str(rp.player.nfl_team))
            if not abbr or abbr in team_env:
                continue
            row = next((g for g in sched
                        if abbr in (g.get("home_team"), g.get("away_team"))), None)
            if row is None:
                continue
            env = from_schedule_row(row, abbr)
            if env is None:
                continue
            team_env[abbr] = VegasLine(
                nfl_team=abbr, opponent=env.opponent or "",
                implied_team_total=env.implied_team_total,
                spread=env.spread, over_under=env.total, week=week,
            )
        bundle.vegas = team_env
        bundle.availability.append(SignalAvailability(
            name="vegas_lines", available=len(team_env) > 0, as_of=datetime.utcnow(),
            source="nflverse", note=f"{len(team_env)} teams with lines",
        ))
    except Exception as e:
        bundle.availability.append(SignalAvailability(
            name="vegas_lines", available=False, source="nflverse", note=f"error: {e}"
        ))

    # -- Weather (Open-Meteo, dome-aware) — use each game's HOST stadium --
    try:
        from fantasy_gm.signals.sources.weather import get_weather
        sched = [r for r in nv.schedule_rows(season) if r.get("week") == week]
        abbrs = {ESPN_PRO_TEAM_ABBR.get(str(rp.player.nfl_team))
                 for rp in roster_players if rp.player.nfl_team}
        abbrs.discard(None)
        host_cache: dict[str, object] = {}
        n_weather = 0
        for abbr in abbrs:
            game = next((g for g in sched
                         if abbr in (g.get("home_team"), g.get("away_team"))), None)
            host = game.get("home_team") if game else abbr
            if host not in host_cache:
                host_cache[host] = get_weather(host, week)
            wr = host_cache[host]
            if wr is not None:
                bundle.weather[abbr] = wr
                n_weather += 1
        bundle.availability.append(SignalAvailability(
            name="weather", available=n_weather > 0, as_of=datetime.utcnow(),
            source="open-meteo", note=f"{n_weather} teams (dome-aware)",
        ))
    except Exception as e:
        bundle.availability.append(SignalAvailability(
            name="weather", available=False, source="open-meteo", note=f"error: {e}"
        ))
