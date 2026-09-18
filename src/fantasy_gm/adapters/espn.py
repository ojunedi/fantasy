"""
ESPN Fantasy Football adapter.

Uses the reverse-engineered ESPN API (not officially supported).
Private leagues require SWID and ESPN_S2 cookies from the browser.

Authentication setup:
  1. Log into fantasy.espn.com in Chrome
  2. Open DevTools → Application → Cookies → fantasy.espn.com
  3. Copy the values of `SWID` and `espn_s2`
  4. Set environment variables: ESPN_SWID and ESPN_S2

Rate limits: undocumented. We apply a conservative 1 req/sec default.
"""
from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

from fantasy_gm.adapters.base import FantasyPlatform
from fantasy_gm.adapters.cache import DiskCache
from fantasy_gm.models import (
    FreeAgent,
    LeagueSettings,
    Matchup,
    Platform,
    Player,
    PlayerStatus,
    Position,
    Roster,
    RosterPlayer,
    RosterSlot,
    ScoringRule,
    ScoringRules,
    TeamScore,
    TeamStanding,
    Transaction,
    WaiverType,
)

ESPN_BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{league_id}"

# ESPN slot ID → Position mapping (standard NFL fantasy)
ESPN_SLOT_MAP: dict[int, Position] = {
    0: Position.QB,
    2: Position.RB,
    4: Position.WR,
    6: Position.TE,
    16: Position.DST,
    17: Position.K,
    20: Position.BENCH,
    21: Position.IR,
    23: Position.FLEX,
}

ESPN_POSITION_MAP: dict[int, Position] = {
    1: Position.QB,
    2: Position.RB,
    3: Position.WR,
    4: Position.TE,
    5: Position.K,
    16: Position.DST,
}

ESPN_STATUS_MAP: dict[str, PlayerStatus] = {
    "ACTIVE": PlayerStatus.ACTIVE,
    "QUESTIONABLE": PlayerStatus.QUESTIONABLE,
    "DOUBTFUL": PlayerStatus.DOUBTFUL,
    "OUT": PlayerStatus.OUT,
    "INJURY_RESERVE": PlayerStatus.IR,
    "SUSPENDED": PlayerStatus.SUSPENDED,
}


class ESPNAdapter(FantasyPlatform):
    def __init__(
        self,
        league_id: str,
        cache_dir: Path | None = None,
        cache_ttl: int = 3600,
        request_delay: float = 1.0,
    ):
        self.league_id = league_id
        self._swid = os.environ.get("ESPN_SWID", "")
        self._espn_s2 = os.environ.get("ESPN_S2", "")
        self._delay = request_delay
        cache_path = cache_dir or Path("data/cache/espn")
        self._cache = DiskCache(cache_path, ttl_seconds=cache_ttl)
        self._last_request_at: float = 0.0

    # ------------------------------------------------------------------
    # Internal HTTP
    # ------------------------------------------------------------------

    def _fetch(self, season: int, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, bypass_cache: bool = False) -> dict:
        url = ESPN_BASE.format(season=season, league_id=self.league_id)
        cache_key = f"{season}_{self.league_id}_{sorted((params or {}).items())}"
        if not bypass_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached[0]

        # Rate limiting
        elapsed = time.time() - self._last_request_at
        if elapsed < self._delay:
            time.sleep(self._delay - elapsed)

        cookies = {}
        if self._swid:
            cookies["SWID"] = self._swid
        if self._espn_s2:
            cookies["espn_s2"] = self._espn_s2

        resp = httpx.get(url, params=params, cookies=cookies, headers=headers or {}, timeout=15)
        if resp.status_code in (401, 403):
            raise PermissionError(
                "ESPN auth failed — your espn_s2 cookie has expired or your league is private. "
                "Re-copy ESPN_SWID and ESPN_S2 from browser DevTools and update your .env file."
            )
        resp.raise_for_status()
        self._last_request_at = time.time()

        data = resp.json()
        self._cache.set(cache_key, data)
        return data

    # ------------------------------------------------------------------
    # FantasyPlatform implementation
    # ------------------------------------------------------------------

    def get_league_settings(self, season: int) -> LeagueSettings:
        data = self._fetch(season, params={"view": "mSettings"})
        settings = data.get("settings", {})
        roster_settings = settings.get("rosterSettings", {})
        scoring_settings = settings.get("scoringSettings", {})
        schedule_settings = settings.get("scheduleSettings", {})

        # Build scoring rules from ESPN's scoringItems list
        scoring_items = scoring_settings.get("scoringItems", [])
        rules = [
            ScoringRule(stat=str(item.get("statId", "")), points=float(item.get("points", 0)))
            for item in scoring_items
        ]

        # Build roster slots
        lineup_slot_counts: dict[int, int] = roster_settings.get("lineupSlotCounts", {})
        roster_slots: list[RosterSlot] = []
        for slot_id_str, count in lineup_slot_counts.items():
            slot_id = int(slot_id_str)
            position = ESPN_SLOT_MAP.get(slot_id)
            if position is None or count == 0:
                continue
            is_starter = position not in (Position.BENCH, Position.IR)
            for i in range(count):
                roster_slots.append(RosterSlot(
                    slot_id=f"{slot_id}_{i}",
                    position=position,
                    is_starter=is_starter,
                ))

        # ESPN: playoffs typically start week 15 for 14-week regular season
        reg_season_length = schedule_settings.get("matchupPeriodCount", 14)
        playoff_start = reg_season_length + 1
        playoff_weeks = list(range(playoff_start, 19))
        regular_weeks = list(range(1, playoff_start))

        return LeagueSettings(
            platform=Platform.ESPN,
            league_id=self.league_id,
            season=season,
            team_count=settings.get("size", 12),
            roster_slots=roster_slots,
            scoring_rules=ScoringRules(rules=rules),
            waiver_type=WaiverType.SNAKE,
            faab_budget=None,
            playoff_start_week=playoff_start,
            playoff_weeks=playoff_weeks,
            regular_season_weeks=regular_weeks,
        )

    def get_current_week(self, season: int) -> int:
        """The league's live scoring period, straight off ESPN's payload.

        Read passthrough, not a computation: deriving "this week" from a season
        start date would be a fabricated number the moment ESPN shifts a period.
        """
        data = self._fetch(season, params={"view": "mSettings"})
        return int(data.get("scoringPeriodId") or 1)

    def get_roster(self, team_id: str, week: int, season: int, fresh: bool = False) -> Roster:
        rosters = self.get_all_rosters(week=week, season=season, fresh=fresh)
        for r in rosters:
            if r.team_id == team_id:
                return r
        raise ValueError(f"Team {team_id} not found in week {week} rosters")

    def get_all_rosters(self, week: int, season: int, fresh: bool = False) -> list[Roster]:
        data = self._fetch(season, params={"view": "mRoster", "scoringPeriodId": week}, bypass_cache=fresh)
        teams = data.get("teams", [])
        rosters = []
        for team in teams:
            team_id = str(team["id"])
            team_name = team.get("name", f"Team {team_id}")
            members = data.get("members", [])
            owner_name = next(
                (f"{m.get('firstName','')} {m.get('lastName','')}".strip()
                 for m in members if str(m.get("id")) in team.get("primaryOwner", "")),
                "Unknown",
            )
            roster_entries = team.get("roster", {}).get("entries", [])
            players = []
            for entry in roster_entries:
                slot_id = entry.get("lineupSlotId", 20)
                position = ESPN_SLOT_MAP.get(slot_id, Position.BENCH)
                is_starter = position not in (Position.BENCH, Position.IR)
                pdata = entry.get("playerPoolEntry", {}).get("player", {})
                eligible_ids = pdata.get("eligibleSlots", [])
                eligible = [ESPN_SLOT_MAP[s] for s in eligible_ids if s in ESPN_SLOT_MAP and ESPN_SLOT_MAP[s] not in (Position.BENCH, Position.IR, Position.FLEX, Position.SUPER_FLEX)]
                raw_pos = pdata.get("defaultPositionId", 0)
                primary_pos = ESPN_POSITION_MAP.get(raw_pos, Position.WR)
                status_str = entry.get("playerPoolEntry", {}).get("injuryStatus", "ACTIVE")
                pool = entry.get("playerPoolEntry", {})
                # ESPN sets lineupLocked once the player's game kicks off; it is
                # the same flag behind the 409 TRAN_LINEUP_LOCKED rejection on a
                # write, so it is authoritative about what can still be moved.
                is_locked = bool(pool.get("lineupLocked"))
                # statSourceId 0 is the actual result, 1 is the projection. A
                # player who has not played has no statSourceId 0 row at all,
                # which is exactly how we tell "played" from "projected to".
                actual_points = None
                for stat in pdata.get("stats", []):
                    if (stat.get("statSourceId") == 0
                            and stat.get("scoringPeriodId") == week
                            and stat.get("seasonId") == season):
                        actual_points = round(float(stat.get("appliedTotal", 0.0)), 2)
                        break
                player = Player(
                    platform_id=str(pdata.get("id", "")),
                    name=pdata.get("fullName", "Unknown"),
                    position=primary_pos,
                    eligible_positions=eligible or [primary_pos],
                    nfl_team=str(pdata["proTeamId"]) if pdata.get("proTeamId") else None,
                    status=ESPN_STATUS_MAP.get(status_str, PlayerStatus.ACTIVE),
                )
                players.append(RosterPlayer(
                    player=player,
                    slot=position,
                    is_starter=is_starter,
                    is_locked=is_locked,
                    actual_points=actual_points,
                ))
            rosters.append(Roster(
                team_id=team_id,
                team_name=team_name,
                owner_name=owner_name,
                players=players,
                week=week,
                season=season,
            ))
        return rosters

    def get_matchup(self, team_id: str, week: int, season: int) -> Matchup:
        data = self._fetch(season, params={"view": "mMatchup", "scoringPeriodId": week})
        schedule = data.get("schedule", [])
        for game in schedule:
            if game.get("matchupPeriodId") != week:
                continue
            home = game.get("home", {})
            away = game.get("away", {})
            home_id = str(home.get("teamId", ""))
            away_id = str(away.get("teamId", ""))
            if team_id not in (home_id, away_id):
                continue
            return Matchup(
                week=week,
                season=season,
                home=TeamScore(
                    team_id=home_id,
                    team_name=str(home_id),
                    projected_score=home.get("totalProjectedPointsLive"),
                    actual_score=home.get("totalPoints"),
                ),
                away=TeamScore(
                    team_id=away_id,
                    team_name=str(away_id),
                    projected_score=away.get("totalProjectedPointsLive"),
                    actual_score=away.get("totalPoints"),
                ),
                is_complete=game.get("winner") is not None,
            )
        raise ValueError(f"No matchup found for team {team_id} in week {week}")

    def get_free_agents(
        self,
        week: int,
        season: int,
        position_filter: list[str] | None = None,
    ) -> list[FreeAgent]:
        filter_header: dict = {
            "players": {
                "filterStatus": {"value": ["FREEAGENT", "WAIVERS"]},
                "filterSlotIds": {"value": [0, 2, 4, 6, 16, 17, 23]},  # all eligible slots
                "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
                "limit": 200,
                "offset": 0,
            }
        }
        if position_filter:
            pos_ids = {v: k for k, v in ESPN_POSITION_MAP.items()}
            slot_ids = [pos_ids[p] for p in position_filter if p in pos_ids]
            if slot_ids:
                filter_header["players"]["filterSlotIds"]["value"] = slot_ids

        import json
        data = self._fetch(
            season,
            params={"view": "kona_player_info", "scoringPeriodId": week},
            headers={"X-Fantasy-Filter": json.dumps(filter_header)},
        )
        players_raw = data.get("players", [])
        agents = []
        for entry in players_raw:
            p = entry.get("player", {})
            raw_pos = p.get("defaultPositionId", 0)
            primary_pos = ESPN_POSITION_MAP.get(raw_pos, Position.WR)
            eligible_ids = p.get("eligibleSlots", [])
            eligible = [ESPN_SLOT_MAP[s] for s in eligible_ids if s in ESPN_SLOT_MAP and ESPN_SLOT_MAP[s] not in (Position.BENCH, Position.IR, Position.FLEX, Position.SUPER_FLEX)]
            player = Player(
                platform_id=str(p.get("id", "")),
                name=p.get("fullName", "Unknown"),
                position=primary_pos,
                eligible_positions=eligible or [primary_pos],
                nfl_team=str(p["proTeamId"]) if p.get("proTeamId") else None,
                status=ESPN_STATUS_MAP.get(entry.get("injuryStatus", "ACTIVE"), PlayerStatus.ACTIVE),
            )
            percent_owned = entry.get("onTeamId") and 0.0 or (
                entry.get("playerPoolEntry", {}).get("percentOwned", 0.0)
            )
            agents.append(FreeAgent(
                player=player,
                percent_owned=float(percent_owned or 0.0),
                waiver_priority=entry.get("waiverProcessDate"),
            ))
        return agents

    def get_raw_lineup_slots(self, team_id: str, week: int, season: int) -> dict[str, int]:
        """Map player_id -> current ESPN numeric lineupSlotId for a team.

        The Roster model abstracts slots to Position; the write path needs the
        raw ESPN slot IDs to compute lineup moves.
        """
        data = self._fetch(season, params={"view": "mRoster", "scoringPeriodId": week}, bypass_cache=True)
        slots: dict[str, int] = {}
        for team in data.get("teams", []):
            if str(team["id"]) != team_id:
                continue
            for entry in team.get("roster", {}).get("entries", []):
                pid = str(entry.get("playerPoolEntry", {}).get("player", {}).get("id", ""))
                slots[pid] = entry.get("lineupSlotId", 20)
        return slots

    def get_projections(self, week: int, season: int) -> dict[str, float]:
        """
        ESPN's own projected fantasy points per player for a week, already
        scored under this league's rules.

        ESPN embeds a `stats` array on each player. Entries with
        statSourceId == 1 are projections; statSourceId == 0 are actuals.
        `appliedTotal` is the fantasy-point total under league scoring.

        This is ESPN-specific (not part of FantasyPlatform) — it's a signal
        source, wrapped by signals/projections.py with freshness metadata.
        """
        import json as _json
        # ESPN 400s on a bare {"limit": N} filter — a sort key is required for
        # kona_player_info. sortPercOwned returns every player (ordered by
        # ownership) with their stats array intact, from which we pull the
        # week's projection (statSourceId == 1). Verified live.
        filter_header = {
            "players": {
                "limit": 1500,
                "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
            }
        }
        data = self._fetch(
            season,
            params={"view": "kona_player_info", "scoringPeriodId": week},
            headers={"X-Fantasy-Filter": _json.dumps(filter_header)},
        )
        projections: dict[str, float] = {}
        for entry in data.get("players", []):
            p = entry.get("player", {})
            pid = str(p.get("id", ""))
            for stat in p.get("stats", []):
                if (
                    stat.get("statSourceId") == 1
                    and stat.get("scoringPeriodId") == week
                    and stat.get("seasonId") == season
                ):
                    projections[pid] = round(float(stat.get("appliedTotal", 0.0)), 2)
                    break
        return projections

    def get_actual_scores(self, week: int, season: int) -> dict[str, float]:
        """Actual fantasy points per player for a completed week (statSourceId == 0).

        Used by the backtest harness for outcome measurement only — never as
        a decision input.
        """
        import json as _json
        # Same filter-shape requirement as get_projections: a sort key is
        # mandatory or ESPN returns 400.
        filter_header = {
            "players": {
                "limit": 1500,
                "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
            }
        }
        data = self._fetch(
            season,
            params={"view": "kona_player_info", "scoringPeriodId": week},
            headers={"X-Fantasy-Filter": _json.dumps(filter_header)},
        )
        scores: dict[str, float] = {}
        for entry in data.get("players", []):
            p = entry.get("player", {})
            pid = str(p.get("id", ""))
            for stat in p.get("stats", []):
                if (
                    stat.get("statSourceId") == 0
                    and stat.get("scoringPeriodId") == week
                    and stat.get("seasonId") == season
                ):
                    scores[pid] = round(float(stat.get("appliedTotal", 0.0)), 2)
                    break
        return scores

    def get_standings(self, season: int) -> list[TeamStanding]:
        """Season records, points-for/against, and playoff seed per team.

        Feeds the Supervisor's risk posture (must-win / coast / normal). Uses
        the mTeam view's `record.overall` block plus `playoffSeed`.
        """
        data = self._fetch(season, params={"view": "mTeam"})
        standings: list[TeamStanding] = []
        for team in data.get("teams", []):
            team_id = str(team["id"])
            overall = team.get("record", {}).get("overall", {}) or {}
            standings.append(TeamStanding(
                team_id=team_id,
                team_name=team.get("name", f"Team {team_id}"),
                wins=int(overall.get("wins", 0)),
                losses=int(overall.get("losses", 0)),
                ties=int(overall.get("ties", 0)),
                points_for=float(overall.get("pointsFor", 0.0) or team.get("points", 0.0) or 0.0),
                points_against=float(overall.get("pointsAgainst", 0.0) or 0.0),
                playoff_seed=team.get("playoffSeed"),
                games_back=overall.get("gamesBack"),
            ))
        standings.sort(key=lambda s: (s.playoff_seed if s.playoff_seed else 99))
        return standings

    def get_transactions(self, week: int, season: int) -> list[Transaction]:
        data = self._fetch(season, params={"view": "mTransactions2"})
        raw = data.get("transactions", [])
        txns = []
        for t in raw:
            if t.get("scoringPeriodId") != week:
                continue
            t_type = t.get("type", "").lower()
            normalized = "waiver" if t_type in ("waiver", "freeagent") else t_type
            items = t.get("items", [])
            player_added = None
            player_dropped = None
            for item in items:
                p = item.get("player", {})
                raw_pos = p.get("defaultPositionId", 0)
                player = Player(
                    platform_id=str(p.get("id", "")),
                    name=p.get("fullName", "Unknown"),
                    position=ESPN_POSITION_MAP.get(raw_pos, Position.WR),
                    eligible_positions=[ESPN_POSITION_MAP.get(raw_pos, Position.WR)],
                )
                if item.get("type") == "ADD":
                    player_added = player
                elif item.get("type") == "DROP":
                    player_dropped = player
            ts = t.get("executionType") and datetime.utcnow() or datetime.utcnow()
            txns.append(Transaction(
                transaction_id=str(t.get("id", "")),
                week=week,
                type=normalized,
                team_id=str(t.get("teamId", "")),
                player_added=player_added,
                player_dropped=player_dropped,
                timestamp=ts,
            ))
        return txns
