---
product: Fantasy GM
stage: target-arch
---

# Security

One user, one machine, no multi-tenancy — so most of what this heading usually covers genuinely does not apply. What does apply is narrow and real: the app holds credentials that can modify a real roster, behind a form with no authentication.

## Permissions

| id | role | action | resource | enforced_in |
|----|------|--------|----------|-------------|
| PERM-01 | R-01 | approve or override any recommendation | every decision | `memo/cli.py` and `web/routes/approve.py` — the only paths that set `human_response` |
| PERM-02 | R-01 | authorise a real ESPN write | lineup submission, trade send | The literal `LIVE` typed per execution. Never stored, never a setting |
| PERM-03 | R-02 | read every signal source and compute | all analysis | Unrestricted by design; the agent reads freely and writes nothing |
| PERM-04 | R-02 | execute an irreversible action | nothing | Structurally impossible. The agent's terminal tools only return recommendations; no code path from a tool to an executor exists |

## Secrets

| id | secret | used_by | store | rotation |
|----|--------|---------|-------|----------|
| SEC-01 | ESPN_SWID | SVC-gm | Environment variable | Manual. Rotates whenever ESPN invalidates the session, which it does without warning |
| SEC-02 | ESPN_S2 | SVC-gm | Environment variable | Manual, same trigger as SWID |
| SEC-03 | ANTHROPIC_API_KEY | SVC-gm | Environment variable | Manual |
| SEC-04 | TAVILY_API_KEY | SVC-gm | Environment variable | Manual. Optional — absence degrades a feature rather than breaking the app |

## Protection

| data | at_rest | in_transit | masking |
|------|---------|------------|---------|
| ESPN session cookies | Environment only. Never written to the repo, the database, or a decision snapshot | HTTPS to ESPN | Not logged. The write payload is logged on failure; the cookies are passed separately and are not part of it |
| Decision records | Unencrypted SQLite on a personal machine, and an unencrypted SQL dump in a private git repository the manager owns | Pushed to that repository's remote over whatever transport git is configured with | The dump carries the decisions table only, and is asserted to contain no session cookie, no API key, and no value read from the environment. It is fantasy football scores and the manager's own reasoning, so the exposure is the repository staying private |
| LLM prompts | Not persisted beyond the run checkpoint | HTTPS to the provider | Rosters and projections are sent to the model. Nothing personal beyond the manager's own override text |

## Controls

| id | control | constraint | evidence |
|----|---------|------------|----------|
| CTL-01 | The `fantasy-gm-web` console script binds 127.0.0.1 | CON-02 | `web/app.py:63`, inside `main()`. **This is a default in one entry point, not a control.** `create_app` (`:28`) enforces nothing, so `uvicorn fantasy_gm.web.app:create_app` binds all interfaces with the unauthenticated write form intact |
| CTL-02 | Dry run is the default on every write path | CON-02 | `live: bool = False` on both executors; a real write needs the parameter passed explicitly and the literal typed |
| CTL-03 | The server recomputes every plan; the browser cannot supply moves | CON-02 | D-020. No request payload from the client reaches an executor |
| CTL-04 | Secrets never enter version control | CON-02 | `.gitignore`; read from the environment at construction time |

<!--
CTL-01 is a gap, not a control, and calling it a control was the most dangerous
sentence in the first draft of this file.

The web app holds cookies that can modify a real roster behind a form with no
login. The reasoning was "loopback binding is the access control" — but the
binding lives in a default argument inside the console script's `main()`.
`create_app` is a plain factory, so any other way of serving it (`uvicorn`
directly, a container, a process manager, an IDE run button) listens on all
interfaces with no authentication at all.

The honest statement is: there is no access control. There is one entry point
whose defaults happen to be safe. Enforcing the bind inside `create_app`, or
refusing to start when the host is not loopback and no auth is configured,
would turn this back into the control it was described as.

PERM-04 is worth stating as a permission even though it grants nothing. "The
agent cannot act" is enforced by the absence of a code path rather than by a
check, and absences are easy to fill in later by accident.
-->
