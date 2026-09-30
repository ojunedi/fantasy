---
product: Fantasy GM
stage: vision
---

# Strategy

## Approach

| id | option | status | why |
|----|--------|--------|-----|
| STR-01 | Extend in place | chosen | The domain model is sound, the agent architecture is settled, and the deterministic core already has the right extension points. The gap is feature coverage (waivers, projection quality), not a structural problem |
| STR-02 | Rewrite | rejected | The model is right; a rewrite would cost 247 passing tests and all ESPN auth work for no gain |
| STR-03 | Buy / SaaS | rejected | The point is building the tooling — a bought product removes the interesting problem and gives up the personal performance edge |

## Constraints

| id | kind | constraint | source | implication |
|----|------|-----------|--------|-------------|
| CON-01 | team | Single engineer, part-time project | Personal project | No parallel tracks; new capabilities are sequential. Waiver and projection work cannot both land mid-season |
| CON-02 | commercial | ESPN's write API is reverse-engineered and undocumented | ESPN | Every execution path must default to dry-run; a silent break is always possible. Playwright browser fallback exists for that case |
| CON-03 | deadline | Fantasy decisions only matter during September–January | Season structure | Work done outside the season cannot be validated against real decisions until the next season |
| CON-04 | data | FantasyPros free scraping has rate-limit risk at peak times | FantasyPros | A paid API key or a local cache strategy is needed before FantasyPros becomes the primary projection source |

## Risks

| id | risk | likelihood | impact | response |
|----|------|-----------|--------|----------|
| RISK-01 | ESPN's write endpoint breaks mid-season | medium | medium | Playwright browser fallback already implemented; dry-run default means a break surfaces before it costs a lineup slot |
| RISK-02 | FantasyPros scraping breaks or gets rate-limited | medium | low | ESPN projections are the fallback (already implemented); the signal layer degrades gracefully when a source goes missing |
| RISK-03 | Waiver scope grows beyond the season window | medium | medium | Cap waiver v1: evaluate top-N available players against my roster, surface the single best add, no priority-order modeling |
| RISK-04 | Backtest baseline turns out flat or negative | medium | high | The eval infra exists to find this early; a negative result tells us where the deterministic core needs work before the agent layer matters |
