# Tasks — news-feed

## 1. Reading and grouping

- [x] 1.1 Write `NEWS-01`…`NEWS-06` (integration) in `tests/web/test_news_page.py` with ESPN-shaped articles; clause-annotate (AC-1–AC-7)
- [x] 1.2 Add `fetch_articles` to `signals/news.py`, `news_feed` to `web/reads.py`, `news_view` to `web/context.py`

## 2. The page

- [x] 2.1 Add `GET /news`, `templates/news.html`, the `.news` style and the nav link, following `ux/news.md`

## 3. Verification

- [x] 3.1 Run `uv run pytest`
- [x] 3.2 Run `node scripts/trace.mjs check --phase delivery --change news-feed`
