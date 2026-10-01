---
product: Fantasy GM
stage: target-arch
---

# Architecture Overview

One service. Six contexts. That is not a compromise — it is what a single-user local tool should be, and the folding reason below is the load-bearing part of this file.

## Services

| id | name | contexts | owns | style | folded_reason |
|----|------|----------|------|-------|---------------|
| SVC-gm | Fantasy GM | BC-signal,BC-analysis,BC-lineup,BC-waiver,BC-trade,BC-ledger | AGG-signal-bundle,AGG-lineup-analysis,AGG-waiver-analysis,AGG-trade-analysis,AGG-lineup-decision,AGG-waiver-claim,AGG-trade-offer,AGG-backtest-report | sync | All six contexts are one Python process with two entry points (`fantasy-gm` and `fantasy-gm-web`). Splitting them would buy independent deployment and scaling, and this system needs neither: one user, one league, one laptop, and a decision cadence measured in days. What the contexts buy is *module* boundaries, enforced by import discipline rather than by a network — see `components.md`. The cost of being wrong here is low and reversible; the cost of distributing a single-user tool is a week of plumbing and a permanent debugging tax |

## Cross-cutting

| concern | decision | enforced_in |
|---------|----------|-------------|
| Numeric integrity | Every number is computed in ordinary Python. The model turns language into structured signals and never does arithmetic | `core/` is pure and has no LLM import; the agent reaches numbers only through tool calls |
| Irreversible actions | No write happens without an explicit per-execution confirmation typed by the manager. Dry run is always the default and authorisation is never persisted | `memo/cli.py` gates both the lineup write and the trade send on the literal `LIVE` |
| Write verification | A write is believed only after reading the state back. ESPN can return success without acting | `execute/lineup_plan.py` and `execute/trade_api.py:_confirm_sent` |
| Signal provenance | Every external value carries its source and the time it was taken, inseparably | `models.Signal[T]` has no constructor path without `source` and `as_of` |
| Replay integrity | Every decision stores the inputs it saw, frozen. Nothing rewrites them | `DecisionRecord.inputs_snapshot`, written once at record time |
| Secrets | ESPN session cookies live in the environment, never in the repo or the database | `.gitignore`; read via `os.environ` at executor construction |
| Degradation over failure | A missing signal source is a reason to hedge or abstain, not to crash. The agent says what it could not see | `signals/` returns typed absence; the agent has an `abstain` terminal tool |
| Risk posture | A deterministic `must_win` / `coast` / `normal` posture is computed from record and weeks remaining, and passed into every supervised run as an agent input. It shifts what the agent weighs; it is deliberately *not* baked into the optimizer objective | `agent/supervisor.py:risk_posture`, emitted into runs by `web/runs.py` |
| LLM cost ceiling | A hard call budget per run, shared between the main loop and sub-agents, with one call held in reserve so the agent can always explain itself | `agent/config.py:max_llm_calls`, enforced in `agent/base.py` |
