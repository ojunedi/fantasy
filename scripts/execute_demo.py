"""Live execution demo: show lineup -> make a real swap -> show lineup again."""
import time
from dotenv import load_dotenv
load_dotenv()

from fantasy_gm.adapters.espn import ESPNAdapter
from fantasy_gm.execute.espn_api import ESPNApiExecutor

LEAGUE, TEAM, WEEK, SEASON = "1660218687", "8", 1, 2026

# cache_ttl=0 => every read hits ESPN live, so the "after" reflects the real change
adapter = ESPNAdapter(league_id=LEAGUE, cache_ttl=0)
ex = ESPNApiExecutor(adapter)


def show(title):
    r = adapter.get_roster(TEAM, WEEK, SEASON)
    print(f"\n=== {title} ===")
    for rp in r.starters:
        print(f"  START {rp.slot.value:5} | {rp.player.name} ({rp.player.position.value})")
    print("  bench: " + ", ".join(f"{rp.player.name}" for rp in r.bench))
    return r


before = show("BEFORE")

# Build a clean same-position swap: first bench WR/RB/TE <-> a starter of that position
bench = [rp for rp in before.bench if rp.player.position.value in ("WR", "RB", "TE")]
sub_in = bench[0]
sub_out = next(rp for rp in before.starters
               if rp.player.position == sub_in.player.position)

starters = [rp.player.platform_id for rp in before.starters]
proposed = [sub_in.player.platform_id if pid == sub_out.player.platform_id else pid
            for pid in starters]

print(f"\n>>> SWAP: start {sub_in.player.name}  <->  bench {sub_out.player.name}")

plan = ex.plan_set_lineup(TEAM, WEEK, SEASON, proposed)
for s in plan.human_steps:
    print("   -", s)

result = ex.execute(plan, live=True)   # LIVE write
print(f"\nResult: success={result.success} dry_run={result.dry_run} "
      f"msg={result.message or result.error}")

time.sleep(2)  # allow ESPN read replica to catch up
show("AFTER")
