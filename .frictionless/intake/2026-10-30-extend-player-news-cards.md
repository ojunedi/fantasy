---
date: 2026-10-30
type: extend
confidence: firsthand
relevantTo: event-storm, domain-design, target-arch, feature-slices
---

## Verbatim input

> include a news section, with reports and news on players and teams. Each player should have a card that pops up I can see their statistics over the season fantasy and real stats. I also want a picture for each player in the popup card

## What I take from this

The manager wants three related things in one feature area:

1. **A news section** — a browsable feed of player and team news/reports, distinct from the existing decision brief flow. This is a pull-based research surface, not a push-based recommendation.

2. **Player stat cards** — a popup or overlay that surfaces a player's season-to-date stats (both fantasy points scored and real NFL stats like yards, TDs, targets). This implies per-player lookup, not just aggregate roster-level data.

3. **Player photos** — each card shows the player's headshot image, requiring an external image source (ESPN CDN, Sleeper, or similar sports data provider).

The key distinction from what exists: the current model treats news as one signal among many fed into the analysis engine. This request adds a *browsing mode* — the manager is doing research, not receiving a recommendation. That is a new interaction pattern in the system.
