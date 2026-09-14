"""
Approval CLI.

Presents a DecisionRecord to the human, captures approve / reject / modify and
a free-text override reason, and persists everything to the decision store.
The override reason is the project's most important artifact — read back at
season's end to learn where the agent is systematically wrong.
"""
from __future__ import annotations

from fantasy_gm.db.store import DecisionStore
from fantasy_gm.execute.base import Executor
from fantasy_gm.execute.trade_plan import TradeProposalExecutor
from fantasy_gm.models import DecisionRecord, DecisionType, HumanResponse


def _hr(char: str = "-", n: int = 70) -> str:
    return char * n


def _execute_approved_lineup(
    record: DecisionRecord,
    executor: Executor,
    team_id: str,
) -> None:
    """Plan the approved lineup and execute it (dry-run unless confirmed live)."""
    rec = record.modified_recommendation or record.recommendation
    starter_ids = rec.get("starter_player_ids", [])
    if not starter_ids:
        print("  (No starter list to execute.)")
        return

    plan = executor.plan_set_lineup(team_id, record.week, record.season, starter_ids)

    print("\n" + _hr())
    print(f"  EXECUTION PLAN via {executor.name}:")
    if plan.is_noop:
        print("    Lineup already matches — nothing to change.")
    else:
        for step in plan.human_steps:
            print(f"    - {step}")
    for note in plan.notes:
        print(f"    note: {note}")
    print(_hr())

    if plan.is_noop:
        return

    go_live = input("\n  Execute for REAL now? Type 'LIVE' to write, anything else = dry run: ").strip()
    live = go_live == "LIVE"
    result = executor.execute(plan, live=live)

    if result.success:
        prefix = "✓ EXECUTED" if not result.dry_run else "✓ DRY RUN"
        print(f"\n  {prefix}: {result.message}")
    else:
        print(f"\n  ✗ Execution failed: {result.error}")
        print("  Falling back to manual — set this lineup in the ESPN app yourself.")


def _render_trade_packages(record: DecisionRecord) -> None:
    rec = record.recommendation
    if rec.get("abstained"):
        print("\n  ⚠  AGENT ABSTAINED\n")
        print(f"  Memo: {record.memo}\n")
        for m in rec.get("missing_information", []):
            print(f"    - {m}")
        if rec.get("what_you_would_need"):
            print(f"\n  Would need: {rec['what_you_would_need']}")
        return
    print(f"\n  Confidence: {record.confidence:.0%}\n")
    print(f"  Memo:\n  {record.memo}\n")
    trades = rec.get("trades", [])
    for i, t in enumerate(trades, 1):
        send = ", ".join(t.get("send_names") or t.get("send_player_ids", []))
        receive = ", ".join(t.get("receive_names") or t.get("receive_player_ids", []))
        print(f"  [{i}] with team {t.get('counterparty_team_id')} "
              f"(confidence {float(t.get('confidence', 0)):.0%})")
        print(f"      SEND:    {send}")
        print(f"      RECEIVE: {receive}")
        print(f"      why:   {t.get('rationale', '')}")
        print(f"      pitch: {t.get('counterparty_pitch', '')}")
    if rec.get("what_would_change_this"):
        print(f"\n  What would change this: {rec['what_would_change_this']}")


def _present_and_approve_trade(record: DecisionRecord, store: DecisionStore) -> DecisionRecord:
    """Approval flow for TRADE decisions. Approve → print the offer to send."""
    store.save(record)
    print("\n" + _hr("="))
    print(f"  GM RECOMMENDATION — Week {record.week}, {record.season} — TRADE")
    print(_hr("="))
    _render_trade_packages(record)

    print("\n" + _hr())
    while True:
        choice = input("\n  [a]pprove / [r]eject / [s]kip? ").strip().lower()
        if choice in ("a", "r", "s"):
            break
        print("  Please enter a, r, or s.")

    if choice == "s":
        print("  Skipped — no human response recorded.")
        return record
    if choice == "r":
        record.human_response = HumanResponse.REJECTED
        reason = input("\n  Why are you rejecting? (logged) > ").strip()
        record.override_reason = reason
        store.record_human_response(record.id, HumanResponse.REJECTED, override_reason=reason)
        print("\n  ✓ Rejection logged.")
        return record

    # Approve → render manual send steps (ESPN needs the counterparty to accept).
    record.human_response = HumanResponse.APPROVED
    store.record_human_response(record.id, HumanResponse.APPROVED)
    print("\n  ✓ Approved.")
    executor = TradeProposalExecutor()
    for i, t in enumerate(record.recommendation.get("trades", []), 1):
        plan = executor.plan(t)
        print("\n" + _hr())
        print(f"  SEND THIS OFFER [{i}] via {executor.name}:")
        for step in plan.human_steps:
            print(f"    - {step}")
        for note in plan.notes:
            print(f"    {note}")
    print(_hr())
    print("  ESPN trades require the other manager to accept — nothing is auto-sent.")
    return record


def present_and_approve(
    record: DecisionRecord,
    store: DecisionStore,
    executor: Executor | None = None,
    team_id: str | None = None,
) -> DecisionRecord:
    """Interactive approval flow. Saves the record and the human response.

    If an executor is provided, an approved/modified lineup is planned and
    executed (dry-run unless the user confirms LIVE)."""
    if record.decision_type == DecisionType.TRADE:
        return _present_and_approve_trade(record, store)

    store.save(record)

    print("\n" + _hr("="))
    print(f"  GM RECOMMENDATION — Week {record.week}, {record.season} — {record.decision_type.value.upper()}")
    print(_hr("="))

    rec = record.recommendation
    if rec.get("abstained"):
        print("\n  ⚠  AGENT ABSTAINED\n")
        print(f"  Memo: {record.memo}\n")
        missing = rec.get("missing_information", [])
        if missing:
            print("  Missing information:")
            for m in missing:
                print(f"    - {m}")
        if rec.get("what_you_would_need"):
            print(f"\n  Would need: {rec['what_you_would_need']}")
    else:
        print(f"\n  Confidence: {record.confidence:.0%}\n")
        print(f"  Memo:\n  {record.memo}\n")
        changes = rec.get("changes_from_current", [])
        if changes:
            print("  Proposed changes vs. current lineup:")
            for c in changes:
                out = c.get("bench_out_player_id", "(open slot)")
                print(f"    START {c.get('start_in_player_id')} "
                      f"(bench {out})")
                print(f"      reason: {c.get('reason')}")
        else:
            print("  No changes — agent endorses the current lineup.")
        names = rec.get("starter_names", [])
        if names:
            print(f"\n  Recommended starters: {', '.join(names)}")
        if rec.get("what_would_change_this"):
            print(f"\n  What would change this: {rec['what_would_change_this']}")

    print("\n" + _hr())
    print("  Staleness of inputs (seconds):")
    for name, age in record.signals_staleness.items():
        print(f"    {name}: {age:.0f}s")
    print(_hr())

    # Capture the decision
    while True:
        choice = input("\n  [a]pprove / [r]eject / [m]odify / [s]kip? ").strip().lower()
        if choice in ("a", "r", "m", "s"):
            break
        print("  Please enter a, r, m, or s.")

    if choice == "s":
        print("  Skipped — no human response recorded.")
        return record

    if choice == "a":
        record.human_response = HumanResponse.APPROVED
        store.record_human_response(record.id, HumanResponse.APPROVED)
        print("\n  ✓ Approved.")
        if executor and team_id and not record.recommendation.get("abstained"):
            _execute_approved_lineup(record, executor, team_id)
        else:
            print("  Set this lineup in the ESPN app (no executor configured).")
        return record

    # Reject or modify both capture an override reason
    if choice == "m":
        record.human_response = HumanResponse.MODIFIED
        print("\n  Enter your modified starters (comma-separated player_ids), "
              "or leave blank to keep the agent's:")
        raw = input("  starters> ").strip()
        modified = None
        if raw:
            modified = {"starter_player_ids": [s.strip() for s in raw.split(",")]}
        reason = input("  Why are you overriding? (this is logged) > ").strip()
        record.override_reason = reason
        record.modified_recommendation = modified
        store.record_human_response(record.id, HumanResponse.MODIFIED,
                                    override_reason=reason,
                                    modified_recommendation=modified)
        print("\n  ✓ Modification logged.")
        if executor and team_id:
            _execute_approved_lineup(record, executor, team_id)
        else:
            print("  Set your lineup in the ESPN app (no executor configured).")
        return record

    # choice == "r"
    record.human_response = HumanResponse.REJECTED
    reason = input("\n  Why are you rejecting? (this is logged) > ").strip()
    record.override_reason = reason
    store.record_human_response(record.id, HumanResponse.REJECTED, override_reason=reason)
    print("\n  ✓ Rejection logged.")
    return record
