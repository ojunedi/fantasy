---
product: Fantasy GM
stage: target-arch
---

# Tech Stack

## Stack

| id | layer | choice | version | applies_to | decision |
|----|-------|--------|---------|------------|----------|
| TS-01 | language | Python | 3.11 | SVC-gm | The deterministic core is numeric and the ecosystem (nflverse, Polars, Pydantic) is Python-native |
| TS-02 | build | uv | — | SVC-gm | Lockfile-based and fast. Lives at `~/.local/bin/uv` and is not on the default PATH — worth knowing before any command fails confusingly |
| TS-03 | framework | LangGraph | 1.x | SVC-gm | D-010. The checkpointer persists graph state per week, which is what makes a run replayable, and the graph makes the propose-approve-execute flow explicit rather than implied by control flow |
| TS-04 | framework | LangChain | — | SVC-gm | Tool binding only. Orchestration layer, never the model provider |
| TS-05 | runtime | Anthropic Claude | claude-haiku-4-5 | SVC-gm | Chosen on observed tool-calling reliability, not on raw capability: Haiku reached the terminal tool consistently and validated lineup legality unprompted, which the free-tier alternatives did not. Pluggable via `FANTASY_GM_PROVIDER` (google, groq) with per-provider rate and token ceilings |
| TS-06 | datastore | SQLite | — | SVC-gm | Two files: the decision log and the LangGraph checkpoints. A single-user tool with no concurrent writers has no reason to run a server |
| TS-07 | cache | Parquet on disk | — | SVC-gm | nflverse pulls are large and change a few times a day. Parquet keeps them columnar and cheap to re-read |
| TS-08 | framework | Polars | — | SVC-gm | Reads nflverse data. Deliberately confined to `signals/sources/` — the core consumes normalised dicts so it stays pure and testable without a dataframe |
| TS-09 | framework | Pydantic | v2 | SVC-gm | The type vocabulary in `models.py` is the contract between every layer |
| TS-10 | framework | httpx | — | SVC-gm | ESPN, Sleeper, FantasyCalc. Sync throughout — there is no concurrency to exploit at this scale |
| TS-11 | framework | tenacity | — | SVC-gm | Retries on the read paths. Deliberately not on the write paths, where a retry could duplicate an action |
| TS-12 | framework | FastAPI | — | SVC-gm | D-020. The web surface is server-rendered; FastAPI is the routing and dependency layer, not an API framework here |
| TS-13 | frontend | Jinja2 + htmx | htmx vendored | SVC-gm | D-020. No Node, no build step. htmx and its SSE extension are vendored into `web/static/` so the app has no frontend toolchain at all |
| TS-14 | runtime | uvicorn | — | SVC-gm | One worker, bound to localhost. Both are load-bearing — see `nfrs.md` |
| TS-15 | testing | pytest | — | SVC-gm | 545 tests. The deterministic core is tested against fixtures with no network |
| TS-16 | framework | nflreadpy | — | SVC-gm | D-018. Free and keyless access to stats, snaps, schedules, Vegas lines, injuries, and the player-id crosswalk |

<!--
The two choices worth questioning later are TS-03 and TS-05.

LangGraph earns its place through the checkpointer and the explicit terminal-tool
contract, but it is the heaviest dependency here by a wide margin. If replay ever
stops mattering, the hand-written loop it replaced was about sixty lines.

D-012 is stale. It argues for Opus 5 with adaptive thinking at high effort,
reasoning that judgement quality matters more than per-call cost for a weekly
decision. The code now defaults to Haiku 4.5 for a better reason than cost:
reliable multi-tool calling is what this agent actually lives on, and that was
settled by observation rather than by assuming the largest model wins. The
decision record should be updated to say so.
-->
