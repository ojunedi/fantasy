# Tasks — player-card

## 1. The card

- [x] 1.1 Write `PCARD-01`…`PCARD-06` (integration) in `tests/web/test_player_card.py`; clause-annotate (AC-1–AC-7)
- [x] 1.2 Add `nflverse.season_totals`, `web/player_card.py`, the `GET /players/{id}/card` route and `partials/player_card.html`

## 2. Opening it

- [x] 2.1 Add the `<dialog>` to `base.html`, the `player_link` macro, and links on the team, waiver and news pages; `.pcard` styles

## 3. Verification

- [x] 3.1 Run `uv run pytest`
- [x] 3.2 Run `node scripts/trace.mjs check --phase delivery --change player-card`
