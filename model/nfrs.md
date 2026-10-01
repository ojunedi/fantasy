---
product: Fantasy GM
stage: target-arch
---

# Non-Functional Requirements

Every number below comes from the code or from league rules. Where something is unmeasured it says so rather than carrying an invented figure.

## Budgets

| id | service | dimension | requirement | measured_how |
|----|---------|-----------|-------------|--------------|
| NFR-01 | SVC-gm | latency | A weekly lineup run completes before the manager loses patience — target under 5 minutes wall clock. Unmeasured; the LLM calls dominate and the deterministic core is milliseconds | Wall clock on `run-week`. No instrumentation exists yet |
| NFR-02 | SVC-gm | latency | A full-season backtest completes in under 2 minutes with a warm parquet cache | Wall clock on `backtest`. A 14-week run against 3 played weeks currently returns in seconds |
| NFR-03 | SVC-gm | throughput | At most 1 ESPN request per second, self-imposed | Enforced by a sleep in `_fetch` at `adapters/espn.py:113-114`; the 1.0s value is a constructor default at `:89` and a caller may pass a smaller one |
| NFR-04 | SVC-gm | throughput | At most 3 LLM calls per run by default, shared between the main loop and sub-agents, with one further call reserved so the agent can always explain itself | `agent/config.py:75`; enforced in `agent/base.py:426` |
| NFR-05 | SVC-gm | throughput | Provider request ceilings: Anthropic 20/min, Google 4/min, Groq 1/min | `agent/config.py:_DEFAULT_MAX_RPM`. Set by free-tier limits, not by choice |
| NFR-06 | SVC-gm | latency | The lineup decision must be executable before Sunday 1 PM kickoff. Missing it forfeits the week | League rules. Nothing currently watches this clock — see H-06 |
| NFR-07 | SVC-gm | latency | The waiver claim must be filed before the Tuesday night deadline | League rules. No waiver path exists yet to hold to it |
| NFR-08 | SVC-gm | availability | No uptime requirement. The tool is started when needed and is expected to be absent otherwise | Not monitored, deliberately |
| NFR-09 | SVC-gm | consistency | A write is believed only after reading state back. A provider success response is never sufficient evidence | `execute/trade_api.py:_confirm_sent`; the lineup path reads the roster back |
| NFR-10 | SVC-gm | durability | Every decision is written to SQLite before its run reports completion | `db/store.py`, called at the gate rather than at run end |
| NFR-11 | SVC-gm | security | The web surface should bind loopback-only with exactly one worker | `web/app.py:63`, inside `main()` only. **Currently a default, not a requirement** — `create_app` enforces neither, so serving the app any other way satisfies this by luck. See the gap note in `security.md` |
| NFR-12 | SVC-gm | consistency | Backtest projections must predate the games they score. One post-hoc value invalidates the run | `eval/backtest.py` as-of filtering; invariant I-14 |

## Scale Envelope

| service | valid_to | revisit_when |
|---------|----------|--------------|
| SVC-gm | One manager, one 12-team league, one season of history, a few decisions per week | A second league or a second manager appears. Every choice here — single process, SQLite, in-memory run registry, one worker, no auth — assumes exactly one of each, and several of them break on the second |

## Data Classification

| data | service | classification | residency | retention |
|------|---------|----------------|-----------|-----------|
| ESPN session cookies | SVC-gm | confidential | Environment variables on one machine | Until ESPN invalidates them |
| Decision records and override reasons | SVC-gm | internal | Local SQLite | Indefinite — the season review is the point |
| LLM API keys | SVC-gm | confidential | Environment variables | Until manually rotated |
| Rosters, projections, league data | SVC-gm | public | Local cache | Until the TTL expires |

## Not Required

| item | why |
|------|-----|
| Uptime target | Started on demand. There is no service to be up |
| Horizontal scaling | One user. The single worker is a requirement, not a limit to be lifted |
| Authentication | Loopback binding is the access control. This stops being true the instant the host changes |
| Multi-region, failover, DR | One laptop. The relevant risk is losing the laptop, which no architecture here addresses |
| Rate limiting inbound | Nothing calls this system |
| Audit log separate from the decision log | The decision log *is* the audit log, and it is the product's primary artifact |
| Encryption at rest | Fantasy football scores on a personal machine. The cookies are the sensitive part and they are not stored |
| Backup of decisions.db | **Not a deliberate decision — a gap.** The one irreplaceable file in the system, holding both the decision log and the computed scorecards, and nothing copies it anywhere |
| Enforced loopback binding | **Also a gap.** Described as the access control for an unauthenticated write form, but implemented as a default argument in a single entry point |
