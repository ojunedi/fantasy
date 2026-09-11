"""Scan the league for favorable RB trade targets given a WR-heavy package to send."""
from dotenv import load_dotenv
load_dotenv()

from fantasy_gm.adapters.espn import ESPNAdapter

LEAGUE, MY_TEAM, WEEK, SEASON = "1660218687", "8", 1, 2026
adapter = ESPNAdapter(league_id=LEAGUE)

rosters = adapter.get_all_rosters(WEEK, SEASON)

for r in rosters:
    tag = " (ME)" if r.team_id == MY_TEAM else ""
    rbs = [rp.player.name for rp in r.players if rp.player.position.value == "RB"]
    wrs = [rp.player.name for rp in r.players if rp.player.position.value == "WR"]
    te = [rp.player.name for rp in r.players if rp.player.position.value == "TE"]
    qb = [rp.player.name for rp in r.players if rp.player.position.value == "QB"]
    print(f"\n--- Team {r.team_id}{tag}: {r.owner_name} ---")
    print(f"  QB: {', '.join(qb)}")
    print(f"  RB ({len(rbs)}): {', '.join(rbs)}")
    print(f"  WR ({len(wrs)}): {', '.join(wrs)}")
    print(f"  TE: {', '.join(te)}")
