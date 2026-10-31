# Design — news-feed

## Context

`signals/news.py` reads `site.api.espn.com/.../nfl/news` for the agent. Each
article carries `headline`, `description`, `published`, `links.web.href`, and
`categories` with `type` `athlete` (`athleteId`) or `team` (`teamId`). The
`team=<id>` parameter filters by team; ESPN team ids equal the roster's
`nfl_team` (proTeamId). `web/deps.ReadCache` memoises reads per process.

---

# Build approach

## Where the code goes

| Concern | Location | Pattern it follows |
| --- | --- | --- |
| Fetching and normalising | `signals/news.py` — `fetch_articles(team_id=None, limit=50)` → list of dicts | Beside `get_nfl_news`, same endpoint |
| Grouping | `web/context.py` — `news_view(articles_by_feed, roster)` | Pure view builder, like the other `*_view` functions |
| Route | `web/routes/pages.py` — `GET /news` | Existing page handlers; reads through `reads` with a 15-minute TTL key |
| Template | `templates/news.html` | `history.html` layout |
| Style | `.news` list in `static/app.css` | Hairline-ruled, like the tables |
| Nav | `base.html` | Existing links |

## Components

| Component | Action | Notes |
| --- | --- | --- |
| `signals/news.py` — `fetch_articles` | MODIFY | Returns `{id, headline, description, url, published, athlete_ids, team_ids}` |
| `web/context.py` — `news_view`, `relative_time` | MODIFY | |
| `web/routes/pages.py` — `news` | MODIFY | |
| `web/reads.py` — `news_feed(cache, team_id)` | MODIFY | 15-minute memo per feed, separate from the read TTL |
| `templates/news.html`, `base.html`, `static/app.css` | CREATE / MODIFY | |
| `tests/web/test_news_page.py` | CREATE | |

## Domain

No aggregate; read only. Grouping: story ids de-duplicated across feeds;
"Your players" when any `athlete_ids` ∩ roster ids; else "Your teams" when any
`team_ids` ∩ roster teams; else "Around the league" (league feed only).
"Your teams" and "Around the league" show their 25 newest stories — twelve
team feeds return a few hundred; "Your players" is never cut.

## Decisions

| Decision | Chosen | Rejected, and why |
| --- | --- | --- |
| Finding my players' news | ESPN's athlete tags | Name matching: brittle; the tags carry the roster's own ids |
| Team news | One `team=` feed per rostered team | League feed only: team stories fall off the 50-item league feed quickly |
| Pacing | 15-minute memo per feed | Every load: a dozen requests per page view |

## Risks

| Risk | Mitigation |
| --- | --- |
| Feed shape changes | Missing fields drop the story, never the page |
| ~12 team requests on a cold load | Memoised 15 minutes; requests are small and keyless |

---

# Test approach

## Scenario coverage

| Scenario | AC | Level | Test file | Test name | Status |
| --- | --- | --- | --- | --- | --- |
| NEWS-01 | AC-1 | integration | `tests/web/test_news_page.py` | `NEWS-01: a story about one of my players is under your players, naming him` | required |
| NEWS-02 | AC-2 | integration | `tests/web/test_news_page.py` | `NEWS-02: a story about my player's team is under your teams` | required |
| NEWS-03 | AC-3 | integration | `tests/web/test_news_page.py` | `NEWS-03: every other story is around the league, and none appears twice` | required |
| NEWS-04 | AC-4, AC-7 | integration | `tests/web/test_news_page.py` | `NEWS-04: each story shows its link, summary, source and time, newest first` | required |
| NEWS-05 | AC-5 | integration | `tests/web/test_news_page.py` | `NEWS-05: opening news twice within 15 minutes asks ESPN once per feed` | required |
| NEWS-06 | AC-6 | integration | `tests/web/test_news_page.py` | `NEWS-06: an unreachable feed leaves the page standing` | required |

Tests patch `fetch_articles` with articles in ESPN's shape (captured live:
`categories` with `athleteId` / `teamId`).

## Not covered by automated tests

| What | Why | How it is checked instead |
| --- | --- | --- |
| Rendering in a browser | No browser harness | Open `/news` once |
