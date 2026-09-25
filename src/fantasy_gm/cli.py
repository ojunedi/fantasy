"""
Top-level CLI.

  run-week   — run the GM agent for a week and go through approval
  backtest   — replay historical weeks against the three baselines
  show-week  — print actual vs optimal lineup for a completed week
"""
from __future__ import annotations

import argparse
import logging
import os

from dotenv import load_dotenv

load_dotenv()


def _parse_weeks(spec: str) -> list[int]:
    """'1-14' or '1,3,5' or '7' -> list of ints."""
    weeks: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-")
            weeks.extend(range(int(lo), int(hi) + 1))
        else:
            weeks.append(int(part))
    return weeks


def cmd_run_week(args: argparse.Namespace) -> None:
    from fantasy_gm.adapters.espn import ESPNAdapter
    from fantasy_gm.agent.config import AgentConfig
    from fantasy_gm.agent.graph import LineupGraphAgent
    from fantasy_gm.agent.tools import LineupToolContext
    from fantasy_gm.db.store import DecisionStore
    from fantasy_gm.execute.espn_api import ESPNApiExecutor
    from fantasy_gm.memo.cli import present_and_approve

    league_id = os.environ.get("ESPN_LEAGUE_ID", "1660218687")
    team_id = os.environ.get("ESPN_TEAM_ID", "8")

    adapter = ESPNAdapter(league_id=league_id)
    settings = adapter.get_league_settings(season=args.season)

    ctx = LineupToolContext(
        adapter=adapter, settings=settings, team_id=team_id,
        week=args.week, season=args.season,
    )

    store = DecisionStore()
    executor = ESPNApiExecutor(adapter)

    if getattr(args, "supervised", False):
        from fantasy_gm.agent.supervisor import GMSupervisor
        supervisor = GMSupervisor(adapter, settings, team_id)
        posture = supervisor.posture(args.week, args.season)
        print(f"Supervisor posture: {posture.posture.upper()} — {posture.rationale}")
        ctx.posture = posture.posture

    print(f"Running GM agent (LangGraph) for week {args.week}, season {args.season}...")
    agent = LineupGraphAgent(AgentConfig())
    record = agent.decide(ctx)

    present_and_approve(record, store, executor=executor, team_id=team_id)


def cmd_propose_trades(args: argparse.Namespace) -> None:
    from fantasy_gm.adapters.espn import ESPNAdapter
    from fantasy_gm.agent.config import AgentConfig
    from fantasy_gm.agent.supervisor import GMSupervisor
    from fantasy_gm.agent.trade.graph import TradeGraphAgent
    from fantasy_gm.agent.trade.tools import TradeToolContext
    from fantasy_gm.db.store import DecisionStore
    from fantasy_gm.memo.cli import present_and_approve

    league_id = os.environ.get("ESPN_LEAGUE_ID", "1660218687")
    team_id = os.environ.get("ESPN_TEAM_ID", "8")

    adapter = ESPNAdapter(league_id=league_id)
    settings = adapter.get_league_settings(season=args.season)

    ctx = TradeToolContext(
        adapter=adapter, settings=settings, team_id=team_id,
        week=args.week, season=args.season,
    )

    posture = GMSupervisor(adapter, settings, team_id).posture(args.week, args.season)
    print(f"Supervisor posture: {posture.posture.upper()} — {posture.rationale}")
    ctx.posture = posture.posture

    if not getattr(args, "no_interview", False):
        from fantasy_gm.memo.interview import interview_trade_preferences
        ctx.preferences = interview_trade_preferences(ctx)

    print(f"Running Trade agent for week {args.week}, season {args.season}...")
    record = TradeGraphAgent(AgentConfig()).decide(ctx)

    store = DecisionStore()
    trade_executor = None
    if getattr(args, "send", False):
        from fantasy_gm.execute.trade_api import ESPNTradeApiExecutor
        trade_executor = ESPNTradeApiExecutor(adapter)
    present_and_approve(record, store, team_id=team_id, trade_executor=trade_executor)


def cmd_show_week(args: argparse.Namespace) -> None:
    from fantasy_gm.adapters.espn import ESPNAdapter
    from fantasy_gm.core.optimizer import optimize_lineup

    league_id = os.environ.get("ESPN_LEAGUE_ID", "1660218687")
    team_id = str(args.team_id) if args.team_id else os.environ.get("ESPN_TEAM_ID", "8")

    adapter = ESPNAdapter(league_id=league_id)

    if args.list_teams:
        all_rosters = adapter.get_all_rosters(week=args.week, season=args.season)
        print(f"\nTeams in league {league_id}, week {args.week}, season {args.season}:\n")
        for r in sorted(all_rosters, key=lambda x: int(x.team_id)):
            print(f"  id={r.team_id:>3}  {r.team_name}  ({r.owner_name})")
        return

    settings = adapter.get_league_settings(season=args.season)
    roster = adapter.get_roster(team_id, args.week, args.season)
    actual_scores = adapter.get_actual_scores(args.week, args.season)
    projections = adapter.get_player_projections(args.week, args.season)

    players = [rp.player for rp in roster.players]

    # Projection-based optimizer: what the optimizer would have recommended pre-game
    proj_map = {p.player_id: p.projected_points for p in projections}
    optimizer_lineup = optimize_lineup(players, proj_map, settings)
    optimizer_starters = {rp.player.platform_id for rp in optimizer_lineup if rp.is_starter}

    # Hindsight optimal: best possible lineup with perfect information
    hindsight_lineup = optimize_lineup(players, actual_scores, settings)
    hindsight_starters = {rp.player.platform_id for rp in hindsight_lineup if rp.is_starter}

    actual_starters = {rp.player.platform_id for rp in roster.players if rp.is_starter}
    actual_total = sum(actual_scores.get(pid, 0.0) for pid in actual_starters)
    optimizer_total = sum(actual_scores.get(pid, 0.0) for pid in optimizer_starters)
    hindsight_total = sum(actual_scores.get(pid, 0.0) for pid in hindsight_starters)

    W = 26
    print(f"\nWeek {args.week} · {args.season}  ({roster.team_name})")
    print()
    print(f"  You started:             {actual_total:.2f}")
    print(f"  Optimizer (pre-game):    {optimizer_total:.2f}  ({optimizer_total - actual_total:+.2f})")
    print(f"  Hindsight optimal:       {hindsight_total:.2f}  ({hindsight_total - actual_total:+.2f})")
    print()

    # Unified player table
    rows = []
    for rp in sorted(roster.players, key=lambda r: (not r.is_starter, r.slot.value)):
        pid = rp.player.platform_id
        score = actual_scores.get(pid, 0.0)
        proj = proj_map.get(pid, 0.0)
        rows.append((rp.slot.value, rp.player.name, proj, score,
                     pid in actual_starters, pid in optimizer_starters, pid in hindsight_starters))

    header = f"  {'Slot':<5} {'Player':<{W}} {'Proj':>5} {'Actual':>6}  {'You':^5}  {'Optim':^5}  {'Best':^5}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    prev_starter = True
    for slot, name, proj, score, in_actual, in_optim, in_best in rows:
        if prev_starter and not in_actual:
            print("  " + "·" * (len(header) - 2))
        prev_starter = in_actual

        you   = "  ▸  " if in_actual else "     "
        optim = "  ▸  " if in_optim  else "     "
        best  = "  ▸  " if in_best   else "     "

        flag = ""
        if in_actual and not in_optim:
            flag = "  ← optimizer: bench"
        elif not in_actual and in_optim:
            flag = "  ← optimizer: start"

        print(f"  {slot:<5} {name:<{W}} {proj:>5.1f} {score:>6.1f}  {you}  {optim}  {best}{flag}")

    print()
    missed = [name for _, name, _, _, in_a, in_o, _ in rows if not in_a and in_o]
    swapped = [name for _, name, _, _, in_a, in_o, _ in rows if in_a and not in_o]
    if missed:
        print(f"  Optimizer would have started: {', '.join(missed)}")
        print(f"  Instead of:                   {', '.join(swapped)}")
    else:
        print("  You matched the optimizer's lineup.")


def cmd_backtest(args: argparse.Namespace) -> None:
    from fantasy_gm.adapters.espn import ESPNAdapter
    from fantasy_gm.db.store import DecisionStore
    from fantasy_gm.eval.backtest import Backtester
    from fantasy_gm.models import PlayerProjection

    league_id = os.environ.get("ESPN_LEAGUE_ID", "1660218687")
    team_id = str(args.team_id) if args.team_id else os.environ.get("ESPN_TEAM_ID", "8")

    adapter = ESPNAdapter(league_id=league_id)
    settings = adapter.get_league_settings(season=args.season)

    def projection_fetcher(week: int, season: int) -> list[PlayerProjection]:
        return adapter.get_player_projections(week, season)

    def actual_score_fetcher(week: int, season: int) -> dict[str, float]:
        return adapter.get_actual_scores(week, season)

    backtester = Backtester(
        platform=adapter, team_id=team_id, settings=settings,
        projection_fetcher=projection_fetcher,
        actual_score_fetcher=actual_score_fetcher,
    )
    weeks = _parse_weeks(args.weeks)
    result = backtester.run_season(weeks, args.season)

    store = DecisionStore()
    for sc in result.weeks:
        store.save_scorecard(sc)

    print("\n=== Backtest Summary ===")
    for k, v in result.summary().items():
        print(f"  {k}: {v}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # Quiet per-request HTTP spam so the agent trace stays readable.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(prog="fantasy-gm")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run-week", help="Run the GM agent for a week")
    p_run.add_argument("--week", type=int, required=True)
    p_run.add_argument("--season", type=int, default=2026)
    p_run.add_argument("--supervised", action="store_true",
                       help="Set risk posture from standings via the GM Supervisor.")
    p_run.set_defaults(func=cmd_run_week)

    p_trade = sub.add_parser("propose-trades", help="Run the Trade agent for a week")
    p_trade.add_argument("--week", type=int, required=True)
    p_trade.add_argument("--season", type=int, default=2026)
    p_trade.add_argument("--no-interview", action="store_true",
                         help="Skip the trade brief and run the standard scan.")
    p_trade.add_argument("--send", action="store_true",
                         help="Enable sending an approved offer via ESPN's API "
                              "(still gated on typing LIVE).")
    p_trade.set_defaults(func=cmd_propose_trades)

    p_show = sub.add_parser("show-week", help="Print actual vs optimal lineup for a completed week")
    p_show.add_argument("--week", type=int, required=True)
    p_show.add_argument("--season", type=int, default=2025)
    p_show.add_argument("--team-id", type=int, default=None, help="Override team ID (default: ESPN_TEAM_ID env var)")
    p_show.add_argument("--list-teams", action="store_true", help="List all teams for this week/season and exit")
    p_show.set_defaults(func=cmd_show_week)

    p_bt = sub.add_parser("backtest", help="Replay historical weeks vs. baselines")
    p_bt.add_argument("--season", type=int, default=2025)
    p_bt.add_argument("--weeks", type=str, default="1-14")
    p_bt.add_argument("--team-id", type=int, default=None, help="Override team ID (default: 8)")
    p_bt.set_defaults(func=cmd_backtest)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
