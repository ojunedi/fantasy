# UX — news-feed

> **Design system:** none registered — follows the existing pages (section
> heads, hairline-ruled lists, `.note`, `.stamp`).
> **Prototype:** no prototype exists — not reviewed by clicking through.

## Screen: News · route `/news` · not prototyped

| State | Trigger | What the manager sees |
| --- | --- | --- |
| Loaded | Feeds read | Three sections — **Your players**, **Your teams**, **Around the league** — each a list of stories |
| A section empty | No story in it | The section heading with "Nothing about your players in the latest news." / "…your teams…" / "…around the league…" |
| Feed unreachable | League feed failed | Banner: "Couldn't load ESPN's news — try again in a minute." Team sections still shown if their feeds loaded |

Each story:

```
Kyle Pitts is heating up in the red zone for Atlanta     ← link to ESPN, opens in a new tab
Your player: Kyle Pitts · ESPN · 2h ago                  ← "Your player:" only in that section
Short summary from ESPN…
```

## Components

| Element | Build as | Source |
| --- | --- | --- |
| Section | `section__head` + `<ul class="news">` | Existing section head; NEW: a small `.news` list style, hairline-ruled like the tables |
| Story | `<li>` with `<a target="_blank" rel="noopener">`, `.stamp` meta line, `<p>` summary | Existing classes |
| Unreachable | `<div class="banner">` | Existing banner |
| Nav | "News" link in `base.html` | Existing nav |

## Content

| Element | String |
| --- | --- |
| Headings | "Your players" · "Your teams" · "Around the league" |
| Meta | "Your player: {names} · ESPN · {relative time}" / "{team} · ESPN · {relative time}" / "ESPN · {relative time}" |
| Empty | "Nothing about your players in the latest news." etc. |
| Unreachable | "Couldn't load ESPN's news — try again in a minute." |
