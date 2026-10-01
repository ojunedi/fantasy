---
product: Fantasy GM
stage: target-arch
---

# Integration

Six external systems, none of them with a contract we can rely on. The field-level mapping lives in `contexts.md#ACL Mappings`; this file is what happens when each one fails.

## Integrations

| id | system | direction | protocol | pattern | auth | on_failure |
|----|--------|-----------|----------|---------|------|------------|
| INT-01 | SYS-ESPN | inbound | HTTPS JSON | acl | none for reads | Serve from the TTL cache and mark the signal stale. If nothing is cached, the roster is unknown and the run abstains rather than guessing |
| INT-02 | SYS-ESPN | outbound | HTTPS JSON | acl | SWID + espn_s2 session cookies | Lineup: fall back to browser automation, then tell the manager to act manually. Trade: report the send unconfirmed and explicitly do not retry — a duplicate offer is worse than an unverified one |
| INT-03 | SYS-NFLVERSE | inbound | HTTPS parquet | conformist | none | Serve the parquet cache past its TTL and mark it stale. Usage and schedule grades degrade rather than vanish |
| INT-04 | SYS-FANTASYCALC | inbound | HTTPS JSON | conformist | none | Report values unavailable. Every value column is dropped from the brief rather than showing a cached price as current |
| INT-05 | SYS-ESPN-NEWS | inbound | HTTPS JSON | conformist | none | Skip the news interpretation sub-agent. The agent notes it had no news and weights injury signals accordingly |
| INT-06 | SYS-TAVILY | inbound | HTTPS JSON | conformist | API key, optional | Degrade with an explicit message. Absence of a research channel is a reason to hedge, never an error |
| INT-07 | SYS-WEATHER | inbound | HTTPS JSON | conformist | none | Drop the game-environment adjustment. Dome games are unaffected either way |

<!--
The direction split on ESPN is the important row. Reads are unauthenticated and
cacheable; writes need session cookies and cannot be retried safely. Treating
them as one integration is how a read-path retry policy ends up applied to a
write.

Everything except the two ESPN rows is `conformist`: we accept these models
exactly as they arrive and absorb their churn, because there is no leverage to
do otherwise and no cost to being a passive consumer. Only ESPN gets an
anti-corruption layer, and only because its shapes are undocumented, lossy, and
load-bearing — six of the eight field mappings lose something.
-->
