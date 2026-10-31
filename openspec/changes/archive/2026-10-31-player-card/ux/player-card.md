# UX — player-card

> **Design system:** none registered — follows the existing pages.
> **Prototype:** no prototype exists — not reviewed by clicking through.

## Component: Player card · opened over any page · not prototyped

| State | Trigger | What the manager sees |
| --- | --- | --- |
| Loading | Name clicked | The card frame with "Loading…" |
| Loaded | Data read | Photo, name, position · team; **Fantasy points** row of weeks; **Season stats** table; **Recent news** list; a close button |
| No photo | Image fails or a defense | Team logo (defense) or initials in a circle |
| No stats | nflverse has no rows for him | "No season stats yet." under Season stats |
| No news | No tagged stories | "No recent headlines." |
| Unknown player | Id not found | "No card for this player." |

Layout:

```
┌──────────────────────────────────────────────┐
│ [photo]  Bijan Robinson                    × │
│          RB · ATL                            │
│ Fantasy points (ESPN, league scoring)        │
│  W1 21.4  W2 18.0  W3 —  W4 30.2 …           │
│ Season stats · through week 8 · nflverse     │
│  Rush 112-604-5   Rec 31-288-2   Tgt 38      │
│ Recent news                                  │
│  How the Falcons' two biggest stars bond… 2d │
└──────────────────────────────────────────────┘
```

## Components

| Element | Build as | Source |
| --- | --- | --- |
| Card | `<dialog id="player-card">` in `base.html`, filled by htmx, shown with `showModal()` | NEW COMPONENT `.pcard` |
| Name link | `<a class="player-link" hx-get="/players/{id}/card" hx-target="#player-card">` | NEW: macro `player_link` |
| Weeks | `<table>` one row | Existing table style |
| News | `.news` list | From the news slice |

## Content

| Element | String |
| --- | --- |
| Points heading | "Fantasy points · ESPN, league scoring" |
| Stats heading | "Season stats · through week {n} · nflverse" |
| Empty stats | "No season stats yet." |
| Empty news | "No recent headlines." |
| Unknown | "No card for this player." |
