"""Revert to the original lineup: start Jameson Williams, bench DK Metcalf."""
import time
from dotenv import load_dotenv
load_dotenv()

from fantasy_gm.adapters.espn import ESPNAdapter
from fantasy_gm.execute.espn_api import ESPNApiExecutor

LEAGUE, TEAM, WEEK, SEASON = "1660218687", "8", 1, 2026
adapter = ESPNAdapter(league_id=LEAGUE, cache_ttl=0)
ex = ESPNApiExecutor(adapter)


def show(title):
    r = adapter.get_roster(TEAM, WEEK, SEASON)
    print(f"\n=== {title} ===")
    for rp in r.starters:
        print(f"  START {rp.slot.value:5} | {rp.player.name} ({rp.player.position.value})")
    print("  bench: " + ", ".join(rp.player.name for rp in r.bench))
    return r


before = show("CURRENT")

by_name = {rp.player.name: rp.player.platform_id for rp in before.players}
jameson = by_name["Jameson Williams"]
metcalf = by_name["DK Metcalf"]

starters = [rp.player.platform_id for rp in before.starters]
proposed = [jameson if pid == metcalf else pid for pid in starters]

print(f"\n>>> REVERT: start Jameson Williams  <->  bench DK Metcalf")
plan = ex.plan_set_lineup(TEAM, WEEK, SEASON, proposed)
for s in plan.human_steps:
    print("   -", s)

result = ex.execute(plan, live=True)
print(f"\nResult: success={result.success} msg={result.message or result.error}")

time.sleep(2)
show("RESTORED (original)")
