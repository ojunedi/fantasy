"""Quick smoke test — pulls live data from ESPN and prints what we got."""
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from fantasy_gm.adapters.espn import ESPNAdapter

LEAGUE_ID = "1660218687"
TEAM_ID = "8"
SEASON = 2026

adapter = ESPNAdapter(league_id=LEAGUE_ID, cache_dir=Path("data/cache/espn"))

print("=== League Settings ===")
try:
    settings = adapter.get_league_settings(season=SEASON)
    print(f"Platform:     {settings.platform.value}")
    print(f"Teams:        {settings.team_count}")
    print(f"Waiver type:  {settings.waiver_type.value}")
    print(f"Playoff start week: {settings.playoff_start_week}")
    starter_slots = [s for s in settings.roster_slots if s.is_starter]
    print(f"Starter slots ({len(starter_slots)}): {[s.position.value for s in starter_slots]}")
    scoring_sample = settings.scoring_rules.rules[:5]
    print(f"Scoring rules (first 5): {[(r.stat, r.points) for r in scoring_sample]}")
except Exception as e:
    print(f"ERROR: {e}")

print()
print("=== My Roster (Week 1) ===")
try:
    roster = adapter.get_roster(team_id=TEAM_ID, week=1, season=SEASON)
    print(f"Team: {roster.team_name} (owner: {roster.owner_name})")
    print(f"Starters ({len(roster.starters)}):")
    for rp in roster.starters:
        print(f"  [{rp.slot.value:5}] {rp.player.name} ({rp.player.position.value}) — {rp.player.nfl_team} — {rp.player.status.value}")
    print(f"Bench ({len(roster.bench)}):")
    for rp in roster.bench:
        print(f"  [BENCH] {rp.player.name} ({rp.player.position.value}) — {rp.player.status.value}")
except Exception as e:
    print(f"ERROR: {e}")

print()
print("=== Free Agents (top 10 by ownership) ===")
try:
    agents = adapter.get_free_agents(week=1, season=SEASON)
    for fa in agents[:10]:
        print(f"  {fa.player.name:25} {fa.player.position.value:4} {fa.player.nfl_team or '?':5} owned={fa.percent_owned:.1f}%")
except Exception as e:
    print(f"ERROR: {e}")
