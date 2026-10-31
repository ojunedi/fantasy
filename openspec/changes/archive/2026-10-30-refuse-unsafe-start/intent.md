# Intent — refuse-unsafe-start

## Outcome

However the web app is started — `fantasy-gm-web`, `uvicorn` by hand, an IDE
run button, a container — it serves only requests made on this machine to
`localhost`. A request arriving any other way gets a refusal that says why,
and never reaches a page, the approval gate or a write.

## Who

**Actor:** the manager
**What changes for them:** nothing, using it as they do today. What changes
is that the safety no longer rests on one launcher's default: the app itself
holds it.

## Why now

The architecture called the loopback bind "the access control", but it is a
default argument in `main()`; `create_app` enforces nothing. Behind it is an
unauthenticated form holding cookies that can change a real roster. Low
likelihood on a laptop, and small — relying on a default for a season is
different from deciding to.

## Acceptance criteria

| # | Criterion | Source |
| --- | --- | --- |
| AC-1 | A request that reaches the app on any network address other than a loopback address is refused with 403 and a plain reason, and no route runs | NFR-11; invariant I-11 |
| AC-2 | A request on a loopback address whose `Host` names anything but `localhost`, `127.0.0.1` or `::1` is refused the same way — so a web page cannot reach the app through the browser by pointing its own domain name at this machine (DNS rebinding) | invariants I-11, I-24 |
| AC-3 | The check lives in the app the factory builds, so every way of starting it is covered, including `uvicorn fantasy_gm.web.app:create_app --factory --host 0.0.0.0` | outcome; resolves the slice's open question |
| AC-4 | Requests on a loopback address naming `localhost`, `127.0.0.1` or `::1`, with or without a port, are served exactly as today | outcome |
| AC-5 | Every refusal is written to standard error with the address and host it arrived on, so a misconfigured start is visible in the terminal | outcome |

## Acceptance signal

- Started with `--host 0.0.0.0`, the app answers from this machine and
  refuses from a phone on the same Wi-Fi.

## Out of scope

- Authentication, and any way to serve beyond this machine. The slice allows
  "unless authentication is configured"; nothing needs remote access, so no
  such override is built.
- Changing how `fantasy-gm-web` starts.

## Carried context

| | |
| --- | --- |
| **Bounded contexts** | Lineup Execution and Trade Execution — their gates are what the web form exposes |
| **Aggregates touched** | None |
| **Invariants at risk** | No write without an approval the manager gave (I-11); the person typing `LIVE` is the manager (I-24) |
| **Contracts** | None external |
| **NFRs that apply** | Loopback only, one worker (NFR-11) |
| **Depends on** | Nothing |

## Interface impact

**Does this slice touch a user interface?** No. The app's pages are
unchanged; a refused request gets a plain-text 403.

## Open questions

| # | Question | Owner | Blocking? |
| --- | --- | --- | --- |
| Q-1 | Enforce in the factory, or a startup check with an override? **Resolved: in the factory**, per request — the safe path is unavoidable, and there is no override because no remote use exists | — | No |
