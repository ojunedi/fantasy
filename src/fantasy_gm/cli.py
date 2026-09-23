"""
Top-level CLI.

  run-week   — run the GM agent for a week and go through approval
  backtest   — replay historical weeks against the three baselines
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
    present_and_approve(record, store, team_id=team_id)


def cmd_backtest(args: argparse.Namespace) -> None:
    from fantasy_gm.adapters.espn import ESPNAdapter
    from fantasy_gm.db.store import DecisionStore
    from fantasy_gm.eval.backtest import Backtester
    from fantasy_gm.models import PlayerProjection

    league_id = os.environ.get("ESPN_LEAGUE_ID", "1660218687")
    team_id = os.environ.get("ESPN_TEAM_ID", "8")

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
    p_trade.set_defaults(func=cmd_propose_trades)

    p_bt = sub.add_parser("backtest", help="Replay historical weeks vs. baselines")
    p_bt.add_argument("--season", type=int, default=2025)
    p_bt.add_argument("--weeks", type=str, default="1-14")
    p_bt.set_defaults(func=cmd_backtest)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
