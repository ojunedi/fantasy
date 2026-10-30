"""macOS notification delivery for the pre-kickoff nudge."""
from __future__ import annotations

import subprocess


class NudgeDeliveryFailed(Exception):
    pass


class MacNotifier:
    def notify(self, minutes_remaining: float) -> None:
        hours = int(minutes_remaining // 60)
        mins = int(minutes_remaining % 60)
        time_str = f"{hours}h {mins}m" if hours else f"{mins}m"

        body = f"Lineup recommendation unread — kickoff in {time_str}"
        subtitle = "Run fantasy-gm-web and go to Decisions to review"
        script = (
            f'display notification "{body}" '
            f'with title "Fantasy GM" subtitle "{subtitle}"'
        )
        result = subprocess.run(["osascript", "-e", script], capture_output=True)
        if result.returncode != 0:
            raise NudgeDeliveryFailed(result.stderr.decode().strip() or "osascript failed")
