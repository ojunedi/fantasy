# Design — player-card

## Context

`ESPNAdapter.get_actual_scores(week, season)` returns league-scored actuals
for every player that week, from the cached weekly read.
`ESPNAdapter.get_player_projections` gives each player's name and position.
`nflverse.load_player_stats(season)` holds weekly real stats keyed by
`gsis_id`; `build_id_map()` maps ESPN ids to it. `signals/news.cached_articles`
(news slice) gives stories with athlete tags. Photos:
`a.espncdn.com/i/headshots/nfl/players/full/{id}.png`; logos:
`a.espncdn.com/i/teamlogos/nfl/500/{abbr}.png`. A defense's ESPN id is
`-(16000 + proTeamId)`.

---

# Build approach

## Where the code goes

| Concern | Location | Pattern it follows |
| --- | --- | --- |
| Assembling the card | `web/player_card.py` — `build_card(adapter, player_id, season, current_week)` | A view builder like `context.py`, kept in its own module |
| Completed-week memo | `web/player_card.weekly_actuals` — process memo for weeks before the current one | Completed weeks never change |
| Season totals | `nflverse.season_totals(gsis_id, season)` | Beside `player_stat_rows` |
| Route | `web/routes/pages.py` — `GET /players/{id}/card` | Partial page, like other htmx partials |
| Template | `partials/player_card.html`; `<dialog>` + small script in `base.html` | New |
| Links | `_macros.player_link`; used in `_macros.player_row`, `partials/waiver_status.html`, `news.html` | Shared macro |

## Components

| Component | Action | Notes |
| --- | --- | --- |
| `web/player_card.py` | CREATE | |
| `signals/sources/nflverse.py` — `season_totals` | MODIFY | |
| `web/routes/pages.py` — `player_card` | MODIFY | |
| `templates/partials/player_card.html` | CREATE | NEW COMPONENT `.pcard` |
| `templates/_macros.html` — `player_link` | MODIFY | |
| `templates/base.html` — dialog | MODIFY | |
| `templates/partials/waiver_status.html`, `news.html` | MODIFY | Names become links |
| `web/context.news_view` | MODIFY | Keeps player ids beside names |
| `static/app.css` — `.pcard`, `.player-link` | MODIFY | |
| `tests/web/test_player_card.py` | CREATE | |

## Domain

None; read only. Stats shown per position: QB passing and rushing; RB/WR/TE
rushing and receiving; K field goals. Headlines come from the league feed and
the player's own team feed — the 50-story league feed rarely keeps a
player's news for long (nflverse's "LA" is ESPN's "LAR").

## Decisions

| Decision | Chosen | Rejected, and why |
| --- | --- | --- |
| Fantasy points | ESPN actuals | Computed from nflverse: would need the league's 46 scoring rules reimplemented |
| Card shell | One `<dialog>` in the base page | A page per player: loses the page underneath |
| Names | team, waiver, news pages | Decision/trade pages: names come from snapshots; later |

## Risks

| Risk | Mitigation |
| --- | --- |
| First card reads up to eight weekly payloads | Each is the cached weekly read; memoised for the process |
| Photo hotlinking | The browser fetches a public CDN image; no credential travels |

---

# Test approach

## Scenario coverage

| Scenario | AC | Level | Test file | Test name | Status |
| --- | --- | --- | --- | --- | --- |
| PCARD-01 | AC-1, AC-2, AC-3 | integration | `tests/web/test_player_card.py` | `PCARD-01: a player's card shows his photo, weekly points and season stats` | required |
| PCARD-02 | AC-1 | integration | `tests/web/test_player_card.py` | `PCARD-02: a defense shows its team logo` | required |
| PCARD-03 | AC-4 | integration | `tests/web/test_player_card.py` | `PCARD-03: recent headlines are those tagged with him` | required |
| PCARD-04 | AC-5 | integration | `tests/web/test_player_card.py` | `PCARD-04: names on the team, waiver and news pages open the card` | required |
| PCARD-05 | AC-6 | integration | `tests/web/test_player_card.py` | `PCARD-05: an unknown player gets a short message` | required |
| PCARD-06 | AC-7 | integration | `tests/web/test_player_card.py` | `PCARD-06: completed weeks are read once` | required |

## Not covered by automated tests

| What | Why | How it is checked instead |
| --- | --- | --- |
| The dialog opening in a browser | No browser harness | Open the team page and click a name |
