"""macOS notification delivery — the one channel that reaches the manager.

Used by the pre-kickoff nudge and by the failed-write alert; a second channel
would be a second thing to keep working.
"""
from __future__ import annotations

import subprocess


class NudgeDeliveryFailed(Exception):
    pass


def _applescript_string(text: str) -> str:
    """A double-quoted AppleScript literal; a quote in a player's name must not end it."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


class MacNotifier:
    def send(self, body: str, subtitle: str = "") -> None:
        script = (f"display notification {_applescript_string(body)} "
                  f'with title "Fantasy GM" subtitle {_applescript_string(subtitle)}')
        result = subprocess.run(["osascript", "-e", script], capture_output=True)
        if result.returncode != 0:
            raise NudgeDeliveryFailed(result.stderr.decode().strip() or "osascript failed")

    def notify(self, minutes_remaining: float) -> None:
        self.send(f"Lineup recommendation unread — kickoff in {format_minutes(minutes_remaining)}",
                  "Run fantasy-gm-web and go to Decisions to review")


def format_minutes(minutes: float) -> str:
    hours = int(minutes // 60)
    mins = int(minutes % 60)
    return f"{hours}h {mins}m" if hours else f"{mins}m"
