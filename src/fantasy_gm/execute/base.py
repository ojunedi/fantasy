"""
Executor abstraction — the pluggable "act" step after human approval.

Every executor is dry-run by default: it computes exactly what it WOULD do and
returns an ExecutionPlan without sending anything. A real write happens only
when live=True is passed AND the caller has confirmed.

Nothing above this layer knows which executor is in use.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LineupMove:
    """One player moving between lineup slots (ESPN numeric slot IDs)."""
    player_id: str
    player_name: str
    from_slot: int
    to_slot: int

    def describe(self, slot_name) -> str:
        return f"{self.player_name}: {slot_name(self.from_slot)} -> {slot_name(self.to_slot)}"


@dataclass
class ExecutionPlan:
    """What an executor intends to do. Machine + human readable."""
    action_type: str                       # "set_lineup" | "waiver_claim" | ...
    moves: list[LineupMove] = field(default_factory=list)
    request_payload: dict[str, Any] | None = None   # the exact API body that would be sent
    human_steps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)   # season/week/team_id for the executor

    @property
    def is_noop(self) -> bool:
        return not self.moves


@dataclass
class ExecutionResult:
    success: bool
    dry_run: bool
    executor: str
    plan: ExecutionPlan
    message: str = ""
    error: str | None = None


class Executor(ABC):
    """Executes an approved decision against a fantasy platform."""

    name: str = "base"

    @abstractmethod
    def plan_set_lineup(
        self, team_id: str, week: int, season: int, starter_player_ids: list[str]
    ) -> ExecutionPlan:
        """Compute the moves needed to make starter_player_ids the starters. No writes."""
        ...

    @abstractmethod
    def execute(self, plan: ExecutionPlan, live: bool = False) -> ExecutionResult:
        """Carry out a plan. live=False (default) performs no external writes."""
        ...
