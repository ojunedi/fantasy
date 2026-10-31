# UX — unread-recommendation-surfaced

> **Design system:** none registered — follows the existing history table.
> **Prototype:** no prototype exists — not reviewed by clicking through.

## Screen: Decisions · route `/history` · not prototyped

One cell changes: **Your call**.

| State | Trigger | What the manager sees |
| --- | --- | --- |
| Missed, recommendation would have gained | Miss recorded, cost > 0 | `missed` tag + "−{cost} proj" |
| Missed, no cost | Miss recorded, cost below 0.05 (the standing lineup projected as well or better) | `missed` tag + "no cost" |
| Missed, responded late | Miss recorded and a response came after kickoff | `missed` tag + cost + "· {response} after kickoff" |
| Not yet decided | No response, no miss recorded (before kickoff, or another run that week was actioned) | "—" as today |
| Approved / overridden / rejected | As today | As today |

## Components

| Element | Build as | Source |
| --- | --- | --- |
| `missed` tag | `<span class="tag tag--alert">missed</span>` | Existing tag |
| Cost | Plain text beside the tag | Existing table cell |

No new components.

## Content

| Element | String |
| --- | --- |
| Tag | "missed" |
| Cost | "−{cost} proj" (one decimal) |
| No cost | "no cost" |
