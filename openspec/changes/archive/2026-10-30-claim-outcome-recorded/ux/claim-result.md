# UX — claim-outcome-recorded

> **Design system:** none registered — choices follow the existing waiver page.
> **Prototype:** no prototype exists — not reviewed by clicking through.

## Screen: Waiver Decision · route `/waiver` · not prototyped

Extends the filed states from the claim-filing slice.

| State | Trigger | What the manager sees | Exits |
| --- | --- | --- | --- |
| Filed · awaiting result | Filing confirmed or unconfirmed, no result recorded | The existing filed message + **Check result** button | → any result state |
| Still pending | Check pressed, claim still pending or not found | Note: "ESPN hasn't processed the claim yet — check again after the waiver window runs." + **Check result** | → any result state |
| Cleared | Result recorded: cleared | "Claim cleared — {add} is on your roster and {drop} was dropped. Filed {rank} of {teams} in priority." | → `/history` |
| Lost to priority | Result recorded: lost | "Claim lost to priority — {winner} got {add}. You were {rank} of {teams}." | → `/history` |
| Failed | Result recorded: failed | "Claim failed — {reason in words}. This wasn't a priority loss." | → `/history` |
| Earlier week's claim | A filed claim from a previous week with no result | A panel above the week's status: "Week {n} claim — add {add}, drop {drop}." + **Check result** | → any result state, in place |
| Cancelled | Result recorded: cancelled | "Claim was cancelled in ESPN." | → `/history` |
| Check failed | The read itself failed | Banner: "Couldn't read the league — try again in a moment." + **Check result** | → any result state |

Every state except **Check failed** has a spec scenario; Check failed is the
same unreadable-league handling the filing step uses.

## Components

| Element | Build as | Source |
| --- | --- | --- |
| Check result | `<form>` + `btn` posting with htmx to the result route, swapping `#waiver-status` | Same pattern as the filing form |
| Result messages | `<div class="panel">` with `tag tag--chyron` (cleared) / `tag tag--quiet` (others) | Existing panel and tags |
| Check failed | `<div class="banner">` | Existing banner |

No new components.

## Content

| Element | String |
| --- | --- |
| Button | "Check result" |
| Still pending | "ESPN hasn't processed the claim yet — check again after the waiver window runs." |
| Cleared | "Claim cleared — {add} is on your roster and {drop} was dropped. Filed {rank} of {teams} in priority." |
| Lost | "Claim lost to priority — {winner} got {add}. You were {rank} of {teams}." |
| Failed | "Claim failed — {reason in words}. This wasn't a priority loss." ("the player you were dropping was no longer on your roster", "the player was no longer available"; an unknown status is shown as ESPN sent it) |
| Lost, no priority recorded | "… Your waiver position wasn't recorded when the claim was filed." |
| Cancelled | "Claim was cancelled in ESPN." |
| Check failed | "Couldn't read the league — try again in a moment." |
