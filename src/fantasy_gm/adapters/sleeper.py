"""
Sleeper Fantasy Football adapter.

Official documented API — no authentication required.
Rate limit: ~1,000 req/min (soft). We apply 0.1s default delay.

Sleeper has no free agent endpoint; we infer free agents by finding
players not on any roster in the league.
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

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
    Transaction,
    WaiverType,
)

SLEEPER_BASE = "https://api.sleeper.app/v1"

SLEEPER_POSITION_MAP: dict[str, Position] = {
    "QB": Position.QB,
    "RB": Position.RB,
    "WR": Position.WR,
    "TE": Position.TE,
    "K": Position.K,
    "DEF": Position.DST,
}

SLEEPER_STATUS_MAP: dict[str, PlayerStatus] = {
    "active": PlayerStatus.ACTIVE,
    "questionable": PlayerStatus.QUESTIONABLE,
    "doubtful": PlayerStatus.DOUBTFUL,
    "out": PlayerStatus.OUT,
    "ir": PlayerStatus.IR,
}


class SleeperAdapter(FantasyPlatform):
    def __init__(
        self,
        league_id: str,
        cache_dir: Path | None = None,
        cache_ttl: int = 3600,
        request_delay: float = 0.1,
    ):
        self.league_id = league_id
        self._delay = request_delay
        cache_path = cache_dir or Path("data/cache/sleeper")
        self._cache = DiskCache(cache_path, ttl_seconds=cache_ttl)
        self._last_request_at: float = 0.0
        self._player_db: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Internal HTTP
    # ------------------------------------------------------------------

    def _get(self, path: str) -> Any:
        cached = self._cache.get(path)
        if cached is not None:
            return cached[0]

        elapsed = time.time() - self._last_request_at
        if elapsed < self._delay:
            time.sleep(self._delay - elapsed)

        resp = httpx.get(f"{SLEEPER_BASE}{path}", timeout=15)
        resp.raise_for_status()
        self._last_request_at = time.time()

        data = resp.json()
        self._cache.set(path, data)
        return data

    def _get_player_db(self) -> dict[str, Any]:
        if self._player_db is None:
            # ~6MB payload — Sleeper recommends caching this for a week
            cache = DiskCache(Path("data/cache/sleeper"), ttl_seconds=7 * 24 * 3600)
            cached = cache.get("players_nfl")
            if cached:
                self._player_db = cached[0]
            else:
                resp = httpx.get(f"{SLEEPER_BASE}/players/nfl", timeout=30)
                resp.raise_for_status()
                self._player_db = resp.json()
                cache.set("players_nfl", self._player_db)
        return self._player_db

    def _make_player(self, player_id: str, pdata: dict) -> Player:
        pos_str = pdata.get("position", "WR")
        position = SLEEPER_POSITION_MAP.get(pos_str, Position.WR)
        eligible_raw = pdata.get("fantasy_positions", [pos_str])
        eligible = [SLEEPER_POSITION_MAP.get(p, Position.WR) for p in eligible_raw]
        status_str = pdata.get("injury_status") or pdata.get("status", "active")
        return Player(
            platform_id=player_id,
            name=f"{pdata.get('first_name','')} {pdata.get('last_name','')}".strip(),
            position=position,
            eligible_positions=eligible,
            nfl_team=pdata.get("team"),
            status=SLEEPER_STATUS_MAP.get(str(status_str).lower(), PlayerStatus.ACTIVE),
        )

    # ------------------------------------------------------------------
    # FantasyPlatform implementation
    # ------------------------------------------------------------------

    def get_league_settings(self, season: int) -> LeagueSettings:
        data = self._get(f"/league/{self.league_id}")
        scoring_settings = data.get("scoring_settings", {})
        roster_positions = data.get("roster_positions", [])

        rules = [
            ScoringRule(stat=stat, points=float(pts))
            for stat, pts in scoring_settings.items()
        ]

        slots: list[RosterSlot] = []
        slot_counts: dict[str, int] = {}
        for pos in roster_positions:
            slot_counts[pos] = slot_counts.get(pos, 0) + 1
        for pos_str, count in slot_counts.items():
            position = SLEEPER_POSITION_MAP.get(pos_str, Position.BENCH)
            is_starter = pos_str not in ("BN", "IR")
            for i in range(count):
                slots.append(RosterSlot(
                    slot_id=f"{pos_str}_{i}",
                    position=position,
                    is_starter=is_starter,
                ))

        total_weeks = int(data.get("settings", {}).get("playoff_week_start", 15)) - 1
        playoff_start = total_weeks + 1
        return LeagueSettings(
            platform=Platform.SLEEPER,
            league_id=self.league_id,
            season=season,
            team_count=int(data.get("total_rosters", 12)),
            roster_slots=slots,
            scoring_rules=ScoringRules(rules=rules),
            waiver_type=WaiverType.FAAB if data.get("settings", {}).get("waiver_type") == 2 else WaiverType.SNAKE,
            faab_budget=data.get("settings", {}).get("waiver_budget"),
            playoff_start_week=playoff_start,
            playoff_weeks=list(range(playoff_start, 19)),
            regular_season_weeks=list(range(1, playoff_start)),
        )

    def get_all_rosters(self, week: int, season: int) -> list[Roster]:
        rosters_data = self._get(f"/league/{self.league_id}/rosters")
        users_data = self._get(f"/league/{self.league_id}/users")
        matchups_data = self._get(f"/league/{self.league_id}/matchups/{week}")
        player_db = self._get_player_db()

        user_map = {u["user_id"]: u.get("display_name", "Unknown") for u in users_data}
        starters_map = {str(m["roster_id"]): set(m.get("starters", [])) for m in matchups_data}

        rosters = []
        for r in rosters_data:
            roster_id = str(r["roster_id"])
            owner_id = r.get("owner_id", "")
            owner_name = user_map.get(owner_id, "Unknown")
            starters = starters_map.get(roster_id, set())

            players: list[RosterPlayer] = []
            for pid in r.get("players", []):
                pdata = player_db.get(pid, {})
                player = self._make_player(pid, pdata)
                is_starter = pid in starters
                slot = player.position if is_starter else Position.BENCH
                players.append(RosterPlayer(player=player, slot=slot, is_starter=is_starter))

            rosters.append(Roster(
                team_id=roster_id,
                team_name=f"Team {roster_id}",
                owner_name=owner_name,
                players=players,
                week=week,
                season=season,
            ))
        return rosters

    def get_roster(self, team_id: str, week: int, season: int) -> Roster:
        for r in self.get_all_rosters(week=week, season=season):
            if r.team_id == team_id:
                return r
        raise ValueError(f"Team {team_id} not found")

    def get_matchup(self, team_id: str, week: int, season: int) -> Matchup:
        matchups = self._get(f"/league/{self.league_id}/matchups/{week}")
        by_roster: dict[str, dict] = {str(m["roster_id"]): m for m in matchups}
        my = by_roster.get(team_id)
        if not my:
            raise ValueError(f"No matchup for team {team_id} week {week}")
        matchup_id = my["matchup_id"]
        opponent = next(
            (m for rid, m in by_roster.items() if rid != team_id and m.get("matchup_id") == matchup_id),
            None,
        )
        return Matchup(
            week=week,
            season=season,
            home=TeamScore(
                team_id=team_id,
                team_name=f"Team {team_id}",
                actual_score=my.get("points"),
            ),
            away=TeamScore(
                team_id=str(opponent["roster_id"]) if opponent else "unknown",
                team_name=f"Team {opponent['roster_id']}" if opponent else "unknown",
                actual_score=opponent.get("points") if opponent else None,
            ),
            is_complete=my.get("points", 0) > 0,
        )

    def get_free_agents(self, week: int, season: int, position_filter: list[str] | None = None) -> list[FreeAgent]:
        rosters_data = self._get(f"/league/{self.league_id}/rosters")
        player_db = self._get_player_db()
        on_roster: set[str] = set()
        for r in rosters_data:
            on_roster.update(r.get("players", []))

        agents = []
        for pid, pdata in player_db.items():
            if pid in on_roster:
                continue
            pos_str = pdata.get("position", "")
            if position_filter and pos_str not in position_filter:
                continue
            if pos_str not in SLEEPER_POSITION_MAP:
                continue
            agents.append(FreeAgent(player=self._make_player(pid, pdata)))
        return agents

    def get_transactions(self, week: int, season: int) -> list[Transaction]:
        txns_data = self._get(f"/league/{self.league_id}/transactions/{week}")
        player_db = self._get_player_db()
        txns = []
        for t in txns_data:
            adds = t.get("adds") or {}
            drops = t.get("drops") or {}
            t_type = t.get("type", "free_agent")
            normalized = "waiver" if t_type in ("waiver", "free_agent") else t_type
            player_added = None
            player_dropped = None
            if adds:
                pid = next(iter(adds))
                player_added = self._make_player(pid, player_db.get(pid, {}))
            if drops:
                pid = next(iter(drops))
                player_dropped = self._make_player(pid, player_db.get(pid, {}))
            ts = datetime.utcfromtimestamp(t.get("created", 0) / 1000) if t.get("created") else datetime.utcnow()
            txns.append(Transaction(
                transaction_id=str(t.get("transaction_id", "")),
                week=week,
                type=normalized,
                team_id=str(t.get("roster_ids", [None])[0]),
                player_added=player_added,
                player_dropped=player_dropped,
                timestamp=ts,
            ))
        return txns
