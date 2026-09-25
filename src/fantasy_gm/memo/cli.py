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


def _render_no_recommendation(record: DecisionRecord, rec: dict) -> None:
    """Explain why no recommendation came back.

    A deliberate `abstain` and a run that was cut off are different failures and
    must not read the same: the first is the model's judgment, the second is a
    truncated run that may be sitting on usable analysis.
    """
    if rec.get("truncated"):
        print("\n  ⚠  RUN TRUNCATED — no recommendation reached\n")
        print(f"  {record.memo}")
        if rec.get("llm_budget"):
            print(f"  LLM calls used: {rec.get('llm_calls')} of {rec.get('llm_budget')}"
                  " (raise FANTASY_GM_MAX_LLM_CALLS to give the run more room)")
        packages = rec.get("evaluated_packages") or []
        if packages:
            print(f"\n  Packages already evaluated before the cut-off ({len(packages)}) —"
                  " NOT vetted recommendations:")
            for pkg in packages:
                print(f"    · {', '.join(pkg['send_player_ids'])}"
                      f"  ⇄  {', '.join(pkg['receive_player_ids'])}")
                for line in str(pkg.get("evaluation", "")).splitlines():
                    if line.strip():
                        print(f"        {line.strip()}")
        print()
        return

    print("\n  ⚠  AGENT ABSTAINED\n")
    print(f"  Memo: {record.memo}\n")
    for pkg in rec.get("refused_trades", []):
        send = ", ".join(pkg.get("send_names") or pkg.get("send_player_ids", []))
        recv = ", ".join(pkg.get("receive_names") or pkg.get("receive_player_ids", []))
        print(f"  ✗ REFUSED (not offered): {send}  ⇄  {recv}")
    missing = rec.get("missing_information", [])
    if missing:
        print("  Missing information:")
    for m in missing:
        print(f"    - {m}")
    if rec.get("what_you_would_need"):
        print(f"\n  Would need: {rec['what_you_would_need']}")


def _render_trade_packages(record: DecisionRecord) -> None:
    rec = record.recommendation
    if rec.get("abstained"):
        _render_no_recommendation(record, rec)
        return
    if rec.get("selected_deterministically"):
        # The human must know this was scored, not reasoned about — no model
        # vetted the fit, and there is no counterparty pitch.
        print("\n  ⓘ  PICKED BY SCORING, NOT BY THE AGENT")
        print("     The run was cut off before it submitted; these are the "
              "best-scoring\n     packages it had already priced. No written "
              "rationale or pitch.")
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
        for problem in t.get("directive_violations", []):
            print(f"      ⚠  against your brief: {problem}")
    for pkg in rec.get("refused_trades", []):
        send = ", ".join(pkg.get("send_names") or pkg.get("send_player_ids", []))
        recv = ", ".join(pkg.get("receive_names") or pkg.get("receive_player_ids", []))
        print(f"  ✗ REFUSED (not offered): {send}  ⇄  {recv}")
        print(f"      {pkg.get('refused_because', '')}")
    if rec.get("what_would_change_this"):
        print(f"\n  What would change this: {rec['what_would_change_this']}")


def _present_and_approve_trade(
    record: DecisionRecord,
    store: DecisionStore,
    trade_executor=None,
    team_id: str | None = None,
) -> DecisionRecord:
    """Approval flow for TRADE decisions.

    With a trade_executor, an approved package can be sent through ESPN's write
    API behind a LIVE gate; without one, the manual send steps are printed.
    """
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

    record.human_response = HumanResponse.APPROVED
    store.record_human_response(record.id, HumanResponse.APPROVED)
    print("\n  ✓ Approved.")

    trades = record.recommendation.get("trades", [])
    if trade_executor and team_id and trades:
        _send_approved_trade(record, trades, trade_executor, team_id, store)
        return record

    # No executor — render manual send steps.
    executor = TradeProposalExecutor()
    for i, t in enumerate(trades, 1):
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


def _send_approved_trade(record, trades, trade_executor, team_id, store) -> None:
    """Pick one package, plan it, and gate the live send behind typing LIVE.

    Only ever sends ONE offer: firing several at once would commit the same
    players to multiple counterparties simultaneously.
    """
    if len(trades) > 1:
        print(f"\n  {len(trades)} packages proposed. Which one do you want to send?")
        for i, t in enumerate(trades, 1):
            send = ", ".join(map(str, t.get("send_names") or t.get("send_player_ids", [])))
            recv = ", ".join(map(str, t.get("receive_names") or t.get("receive_player_ids", [])))
            print(f"    [{i}] send {send or '(none)'} → get {recv or '(none)'} "
                  f"(team {t.get('counterparty_team_id', '?')})")
        raw = input(f"\n  Package number [1-{len(trades)}], or blank to cancel: ").strip()
        if not raw.isdigit() or not (1 <= int(raw) <= len(trades)):
            print("  Cancelled — nothing sent.")
            return
        index = int(raw) - 1
    else:
        index = 0

    chosen = trades[index]
    # One DecisionRecord holds a single human response, so which package was
    # approved has to be recorded explicitly.
    modified = {"approved_package_index": index}
    record.modified_recommendation = modified
    store.record_human_response(record.id, HumanResponse.APPROVED,
                                modified_recommendation=modified)

    plan = trade_executor.plan(chosen, team_id, record.week, record.season)
    print("\n" + _hr())
    print(f"  TRADE OFFER via {trade_executor.name}:")
    for step in plan.human_steps:
        print(f"    {step}")
    for note in plan.notes:
        print(f"    note: {note}")
    print(_hr())

    if plan.request_payload is None:
        print("  Cannot send this package — see notes above.")
        return

    go_live = input("\n  Send this offer for REAL? Type 'LIVE' to send, anything else = dry run: ").strip()
    result = trade_executor.execute(plan, season=record.season, live=(go_live == "LIVE"))

    if result.success:
        prefix = "✓ SENT" if not result.dry_run else "✓ DRY RUN"
        print(f"\n  {prefix}: {result.message}")
    else:
        print(f"\n  ✗ Send failed: {result.error}")
        print("  Fall back to sending the offer manually in the ESPN app.")


def present_and_approve(
    record: DecisionRecord,
    store: DecisionStore,
    executor: Executor | None = None,
    team_id: str | None = None,
    trade_executor=None,
) -> DecisionRecord:
    """Interactive approval flow. Saves the record and the human response.

    If an executor is provided, an approved/modified lineup is planned and
    executed (dry-run unless the user confirms LIVE)."""
    if record.decision_type == DecisionType.TRADE:
        return _present_and_approve_trade(record, store, trade_executor, team_id)

    store.save(record)

    print("\n" + _hr("="))
    print(f"  GM RECOMMENDATION — Week {record.week}, {record.season} — {record.decision_type.value.upper()}")
    print(_hr("="))

    rec = record.recommendation
    if rec.get("abstained"):
        _render_no_recommendation(record, rec)
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
