---
scope: Fantasy GM
substep: scope
---

# Functions

## Functions

| id | capability | who | function | source |
|----|------------|-----|----------|--------|
| FN-001 | CAP-01 | SYS-ESPN | Fetch league settings, roster slots, and scoring rules | kb |
| FN-002 | CAP-01 | SYS-ESPN | Fetch weekly player projections from ESPN | kb |
| FN-003 | CAP-01 | SYS-NFLVERSE | Fetch player stats, snaps, usage, and opportunity data | kb |
| FN-004 | CAP-01 | SYS-NFLVERSE | Fetch weekly schedule and game site data | kb |
| FN-005 | CAP-01 | SYS-NFLVERSE | Fetch injury report and availability status | kb |
| FN-006 | CAP-01 | SYS-ESPN-NEWS | Fetch player news and practice reports | kb |
| FN-007 | CAP-01 | SYS-FANTASYCALC | Fetch rest-of-season player trade values | kb |
| FN-008 | CAP-01 | SYS-TAVILY | Search web for targeted injury or news context on a specific player | kb |
| FN-009 | CAP-02 | Agent | Compute matchup grade — defense-vs-position relative to league average | kb |
| FN-010 | CAP-02 | Agent | Compute schedule strength for remaining weeks including playoff window (wks 15–17) | kb |
| FN-011 | CAP-02 | Agent | Compute usage and opportunity grade (snaps, targets, carries relative to league average) | kb |
| FN-012 | CAP-02 | Agent | Blend projection signals into a single player score under league scoring rules | kb |
| FN-013 | CAP-02 | Agent | Run lineup optimizer — backtracking constraint search over roster slots | kb |
| FN-014 | CAP-02 | Agent | Evaluate trade packages — RoS projection × positional scarcity × EV delta | kb |
| FN-015 | CAP-02 | Agent | Score waiver add — projected value above replacement given roster need | assumed |
| FN-016 | CAP-02 | Agent | Assess trade fairness and compute impact on optimal starting lineup | kb |
| FN-017 | CAP-03 | Agent | Generate lineup brief with per-player reasoning and signal citations | kb |
| FN-018 | CAP-03 | Agent | Generate trade package with EV case and counterparty pitch | kb |
| FN-019 | CAP-03 | Agent | Generate waiver recommendation with value-above-replacement rationale | assumed |
| FN-020 | CAP-03 | Agent | Generate backtest scorecard — optimizer score vs. naive baseline per week | kb |
| FN-021 | CAP-04 | R-01 | Review lineup recommendation — approve or override with written reason | kb |
| FN-022 | CAP-04 | R-01 | Review trade package — select one package, reject all, or re-brief the agent | kb |
| FN-023 | CAP-04 | R-01 | Review waiver recommendation — approve or skip | assumed |
| FN-024 | CAP-04 | R-01 | Review backtest results and identify which override patterns were correct | kb |
| FN-025 | CAP-05 | SYS-ESPN | Submit approved lineup change via ESPN write API (dry-run default; requires LIVE to execute) | kb |
| FN-026 | CAP-05 | Agent | Generate in-app steps for manager to send trade offer in the ESPN app | kb |
| FN-027 | CAP-05 | Agent | Generate in-app steps for manager to submit waiver claim | assumed |
| FN-028 | CAP-05 | SYS-ESPN | Playwright browser fallback for lineup submission when ESPN write API breaks | kb |
| FN-029 | CAP-06 | Agent | Write DecisionRecord to SQLite with full input snapshot and model reasoning | kb |
| FN-030 | CAP-06 | Agent | Record override reason and original recommendation for end-of-season review | kb |
| FN-031 | CAP-06 | Agent | Run backtest with strict as-of projection data — no post-hoc data leakage | kb |
| FN-032 | CAP-06 | Agent | Compare optimizer score vs. naive (start-platform-rank-one) baseline per week | kb |
| FN-033 | CAP-06 | R-01 | Read override log to identify systematic agent mistakes and calibrate trust | kb |
