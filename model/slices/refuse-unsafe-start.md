---
id: S-009
slice_id: refuse-unsafe-start
status: todo
---

# The app refuses to start in a way that exposes my ESPN cookies

## Outcome

The web application will not serve on a non-loopback interface unless authentication is configured. Starting it any other way — `uvicorn` directly, a container, an IDE run button — either binds loopback or refuses to start with a clear reason.

## Contexts

| id | why |
|----|-----|
| BC-lineup | Hosts the approval and execution gates the web form exposes |
| BC-trade | Same, for the trade send |

## Invariants

| id | risk |
|----|------|
| I-11 | The gate is the only thing preventing an unauthorised write. If the surface is reachable by anyone on the network, the gate is reachable by anyone on the network |
| I-24 | Per-execution confirmation assumes the person confirming is the manager. Nothing currently establishes that |

## NFRs

| id | applies |
|----|---------|
| NFR-11 | This slice is what turns NFR-11 from a description of a default into a requirement the code holds |

## Contracts

No external contracts. This system publishes no API and no messages — the
`Contracts` table is for endpoints and published events, and there are none to
reference. The domain events this slice introduces are internal and already
mapped in `event-maps/`.

## Open questions

| id | question | owner |
|----|----------|-------|
| — | Enforce in `create_app`, or fail fast on a startup check? Enforcing in the factory makes the safe path unavoidable; a check allows a deliberate override with auth configured. The second is more flexible and the first is harder to get wrong | R-01 |

<!--
The architecture pass described the loopback bind as "the access control". It is
a default argument inside `main()` at `web/app.py:63`; `create_app` at `:28`
enforces nothing. So the honest position today is that there is no access
control — there is one entry point whose defaults happen to be safe, in front of
an unauthenticated form holding cookies that can modify a real roster.

Low likelihood on a personal laptop, which is why this is sixth rather than
first. It is in the list because relying on a default for a whole season is a
different thing from deciding to.
-->
