"""Read models: domain objects -> plain dicts the templates render.

This is the only place player-id -> name joins happen, and it is the D-017
guardrail: **nothing here computes an analytic**. Every number it hands to a
template was produced by `core/`, `adapters/`, `signals/`, `execute/`, or `db/`.
What this module does is look up, join, label, and order.

The two things that look like arithmetic are deliberately not analytics:
`projected_score` is called twice (once per lineup) and subtracted, and the
chyron bar width is a fraction of a container. Neither invents a quantity.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fantasy_gm.core.optimizer import (
    live_score,
    locks_from_roster,
    optimize_lineup,
    projected_score,
)
from fantasy_gm.execute.lineup_plan import slot_name
from fantasy_gm.models import (
    DecisionRecord,
    LeagueSettings,
    Matchup,
    Position,
    Roster,
    RosterPlayer,
    TeamStanding,
)

# Starter slots in broadcast order, bench last.
SLOT_ORDER = [
    Position.QB, Position.RB, Position.WR, Position.TE,
    Position.FLEX, Position.SUPER_FLEX, Position.DST, Position.K,
]
_SLOT_RANK = {slot: i for i, slot in enumerate(SLOT_ORDER)}

ALERT_STATUSES = {"out", "ir", "suspended"}


def _team_abbr(nfl_team: str | None) -> str:
    """ESPN stores an NFL team as a numeric proTeamId. "14" means nothing on a
    page, so it is labelled through the existing map rather than shown raw."""
    if not nfl_team:
        return ""
    from fantasy_gm.signals.collector import ESPN_PRO_TEAM_ABBR
    return ESPN_PRO_TEAM_ABBR.get(str(nfl_team), str(nfl_team))


def cache_stamp(adapter: Any, season: int, params: dict) -> float | None:
    """Epoch seconds when this ESPN read was cached, or None if never.

    Mirrors the key `ESPNAdapter._fetch` builds, exactly as `signals/collector.py`
    already does, so the page can always show how old what you're reading is.
    """
    try:
        key = f"{season}_{adapter.league_id}_{sorted(params.items())}"
        return adapter._cache.get_cached_at(key)
    except Exception:
        return None


def _slot_rank(rp: RosterPlayer) -> tuple[int, int]:
    if not rp.is_starter:
        return (99, 0)
    return (_SLOT_RANK.get(rp.slot, 90), 0)


def _player_row(rp: RosterPlayer, projections: dict[str, float],
                opponents: dict[str, str]) -> dict:
    pid = rp.player.platform_id
    status = rp.player.status.value.lower()
    return {
        "player_id": pid,
        # A played player's actual score is a fact; his projection is history.
        "actual": rp.actual_points,
        "has_played": rp.actual_points is not None,
        "is_locked": rp.is_locked,
        "name": rp.player.name,
        "slot": rp.slot.value.upper(),
        "position": rp.player.position.value.upper(),
        "nfl_team": _team_abbr(rp.player.nfl_team),
        "opponent": opponents.get(pid, ""),
        "projection": projections.get(pid),
        "status": status,
        "status_label": "" if status == "active" else status.upper().replace("_", " "),
        "is_alert": status in ALERT_STATUSES,
        "is_starter": rp.is_starter,
    }


def _opponent_map(roster: Roster, signals: Any) -> dict[str, str]:
    """player_id -> the NFL team they face, from the Vegas signal's schedule join.

    Empty when nflverse is unavailable; the column then renders blank rather
    than guessing an opponent.
    """
    if signals is None:
        return {}
    from fantasy_gm.signals.collector import ESPN_PRO_TEAM_ABBR

    out: dict[str, str] = {}
    for rp in roster.players:
        abbr = ESPN_PRO_TEAM_ABBR.get(str(rp.player.nfl_team))
        line = signals.vegas.get(abbr) if abbr else None
        if line is not None and line.opponent:
            out[rp.player.platform_id] = line.opponent
    return out


def roster_view(
    roster: Roster,
    projections: dict[str, float],
    settings: LeagueSettings,
    signals: Any = None,
) -> dict:
    """The roster table plus the optimizer's verdict on it.

    The optimizer's opinion is rendered per row as start/bench, and its total
    gain as one lineup-level number. There is no per-player "delta" here: the
    optimizer scores *lineups*, so a per-player figure would be invented.
    """
    opponents = _opponent_map(roster, signals)
    # Locked players are pinned: a "better" lineup that moves someone whose game
    # has kicked off is one ESPN will reject, so it is not an option to offer.
    locked = locks_from_roster(roster.players)
    optimal = optimize_lineup([rp.player for rp in roster.players], projections,
                              settings, locked=locked)
    optimal_starters = {rp.player.platform_id for rp in optimal if rp.is_starter}
    current_starters = {rp.player.platform_id for rp in roster.players if rp.is_starter}

    rows = []
    for rp in sorted(roster.players, key=_slot_rank):
        row = _player_row(rp, projections, opponents)
        pid = row["player_id"]
        should_start = pid in optimal_starters
        row["optimizer"] = (
            "start" if should_start and not rp.is_starter
            else "bench" if rp.is_starter and not should_start
            else ""
        )
        row["is_swap"] = bool(row["optimizer"])
        rows.append(row)

    current_points = projected_score(roster.players, projections)
    optimal_points = projected_score(optimal, projections)

    # The optimal lineup carries no lock/actual data (optimize_lineup returns
    # fresh RosterPlayers), so the live comparison uses the roster's own rows.
    starter_rows = [rp for rp in roster.players if rp.is_starter]
    played = [rp for rp in starter_rows if rp.actual_points is not None]

    return {
        "starters": [r for r in rows if r["is_starter"]],
        "bench": [r for r in rows if not r["is_starter"]],
        "current_points": current_points,
        "optimal_points": optimal_points,
        "optimizer_gain": optimal_points - current_points,
        "swap_count": len(optimal_starters ^ current_starters) // 2,
        "projected_count": sum(1 for r in rows if r["projection"] is not None),
        "roster_count": len(rows),
        "team_name": roster.team_name,
        "has_opponents": bool(opponents),
        # Live state: banked where games are done, projected where they are not.
        "live_points": live_score(starter_rows, projections),
        "banked_points": sum(rp.actual_points or 0.0 for rp in played),
        "played_count": len(played),
        "starter_count": len(starter_rows),
        "locked_count": len(locked),
        "any_played": bool(played),
        "all_played": bool(starter_rows) and len(played) == len(starter_rows),
    }


def team_live_totals(rosters: list[Roster], projections: dict[str, float]) -> dict[str, dict]:
    """team_id -> live total, banked total, and how much of the lineup has played.

    ESPN's own `totalPoints` on the matchup view reads 0.0 for this league even
    after a game has been played, so the totals shown are summed from the
    rosters with `core.live_score` rather than taken on trust.
    """
    out: dict[str, dict] = {}
    for roster in rosters:
        starters = [rp for rp in roster.players if rp.is_starter]
        played = [rp for rp in starters if rp.actual_points is not None]
        out[roster.team_id] = {
            "live": live_score(starters, projections),
            "banked": sum(rp.actual_points or 0.0 for rp in played),
            "played": len(played),
            "starters": len(starters),
        }
    return out


def chyron_view(
    matchup: Matchup | None,
    team_id: str,
    week: int,
    season: int,
    team_name: str,
    standings: list[TeamStanding] | None = None,
    live_totals: dict[str, dict] | None = None,
) -> dict:
    """The score bar.

    The headline number is **points actually scored** once anybody has played;
    the projected final is secondary. Blending banked and projected points into
    one headline overstates the score — 5.3 scored is not 119.2.

    Before kickoff nobody has scored, so the projection leads instead and is
    labelled as such. There is no win probability anywhere here: the repo has
    no such function and inventing one would violate D-017.
    """
    # Standings carry the real team names; ESPN's mRoster and mMatchup views
    # return a bare id ("Team 8"), so standings win the join when present.
    names = {s.team_id: s.team_name for s in (standings or [])}
    team_name = names.get(team_id) or team_name
    live_totals = live_totals or {}

    def side_view(side, name):
        totals = live_totals.get(side.team_id) if side is not None else None
        if totals is not None:
            return {
                "name": name,
                "scored": totals["banked"],
                "projected": totals["live"],
                "played": totals["played"],
                "starters": totals["starters"],
            }
        fallback = None if side is None else (
            side.actual_score if matchup is not None and matchup.is_complete
            else side.projected_score)
        return {"name": name, "scored": None, "projected": fallback,
                "played": 0, "starters": 0}

    empty_side = {"name": "", "scored": None, "projected": None,
                  "played": 0, "starters": 0, "points": None}

    if matchup is None:
        totals = live_totals.get(team_id)
        mine = {
            "name": team_name,
            "scored": totals["banked"] if totals else None,
            "projected": totals["live"] if totals else None,
            "played": totals["played"] if totals else 0,
            "starters": totals["starters"] if totals else 0,
        }
        played = mine["played"]
        mine["points"] = mine["scored"] if played else mine["projected"]
        return {"has_matchup": False, "week": week, "season": season,
                "state": "live" if played else "proj",
                "any_played": bool(played),
                "mine": mine, "away": dict(empty_side)}

    mine_side = matchup.home if matchup.home.team_id == team_id else matchup.away
    other_side = matchup.away if matchup.home.team_id == team_id else matchup.home

    mine = side_view(mine_side, team_name)
    away = side_view(other_side,
                     names.get(other_side.team_id, f"Team {other_side.team_id}"))

    # How settled this is, so no label overclaims.
    tracked = [s for s in (mine, away) if s["starters"]]
    played = sum(s["played"] for s in tracked)
    starters = sum(s["starters"] for s in tracked)
    if not tracked:
        state = "final" if matchup.is_complete else "proj"
    elif played == 0:
        state = "proj"
    elif played == starters:
        state = "final"
    else:
        state = "live"

    any_played = state in ("live", "final")

    def headline(side):
        return side["scored"] if any_played else side["projected"]

    mine_pts, away_pts = headline(mine), headline(away)

    def margin_of(a, b):
        return None if a is None or b is None else a - b

    # The bar tracks the projected outcome, which is the informative comparison
    # mid-week; the headline numbers are what has actually been scored.
    proj_mine, proj_away = mine["projected"], away["projected"]
    total = (proj_mine or 0) + (proj_away or 0)
    share = (proj_mine / total * 100) if total else 50.0

    return {
        "has_matchup": True,
        "week": week,
        "season": season,
        "is_complete": matchup.is_complete,
        "state": state,
        "any_played": any_played,
        "played": played,
        "total_starters": starters,
        "mine": {**mine, "points": mine_pts},
        "away": {**away, "points": away_pts},
        "margin": margin_of(mine_pts, away_pts),
        "projected_margin": margin_of(proj_mine, proj_away),
        "share": share,
        "bar_left": min(share, 50.0),
        "bar_width": abs(share - 50.0),
    }


def standings_view(standings: list[TeamStanding], my_team_id: str) -> dict:
    """Ranked table with an in-cell points-for bar, scaled to the league leader."""
    top_points = max((s.points_for for s in standings), default=0.0) or 1.0
    rows = []
    for i, s in enumerate(standings, 1):
        rows.append({
            "rank": s.playoff_seed or i,
            "team_id": s.team_id,
            "team_name": s.team_name,
            "standing": s,
            "points_for": s.points_for,
            "points_against": s.points_against,
            "bar_pct": s.points_for / top_points * 100,
            "is_mine": s.team_id == my_team_id,
        })
    return {"rows": rows}


def matchups_view(matchups: list[Matchup], standings: list[TeamStanding],
                  my_team_id: str, live_totals: dict[str, dict] | None = None) -> dict:
    """Two-line rows: every game this week, mine marked.

    Uses the summed live totals where available, for the same reason the chyron
    does — ESPN's `totalPoints` reads 0.0 here.
    """
    names = {s.team_id: s.team_name for s in standings}
    live_totals = live_totals or {}
    rows = []
    for m in matchups:
        sides = []
        for side in (m.home, m.away):
            totals = live_totals.get(side.team_id)
            sides.append({
                "team_id": side.team_id,
                "team_name": names.get(side.team_id, f"Team {side.team_id}"),
                # Same contract as the chyron: scored leads, projected is shown
                # alongside it, and neither is ever presented as the other.
                "scored": totals["banked"] if totals else None,
                "projected": (totals["live"] if totals else
                              (side.actual_score if m.is_complete
                               else side.projected_score)),
                "played": totals["played"] if totals else 0,
                "starters": totals["starters"] if totals else 0,
                "is_mine": side.team_id == my_team_id,
            })

        played = sum(s["played"] for s in sides)
        starters = sum(s["starters"] for s in sides)
        if not starters:
            state = "final" if m.is_complete else "proj"
        elif played == 0:
            state = "proj"
        elif played == starters:
            state = "final"
        else:
            state = "live"

        for side in sides:
            side["points"] = (side["scored"] if state in ("live", "final")
                              else side["projected"])

        rows.append({
            "week": m.week,
            "is_complete": m.is_complete,
            "state": state,
            "is_mine": any(s["is_mine"] for s in sides),
            "sides": sides,
        })
    rows.sort(key=lambda r: (not r["is_mine"],))
    return {"rows": rows}


def rosters_view(rosters: list[Roster], projections: dict[str, float],
                 my_team_id: str, standings: list[TeamStanding] | None = None) -> dict:
    """Every team's roster, collapsed; starters only when expanded.

    As in `chyron_view`, standings supply the real team names — ESPN's mRoster
    view returns a bare id.
    """
    names = {s.team_id: s.team_name for s in (standings or [])}
    out = []
    for roster in sorted(rosters, key=lambda r: int(r.team_id) if r.team_id.isdigit() else 0):
        players = sorted(roster.players, key=_slot_rank)
        out.append({
            "team_id": roster.team_id,
            "team_name": names.get(roster.team_id) or roster.team_name,
            "owner_name": roster.owner_name if roster.owner_name != "Unknown" else "",
            "is_mine": roster.team_id == my_team_id,
            "starters": [_player_row(rp, projections, {}) for rp in players if rp.is_starter],
            "bench": [_player_row(rp, projections, {}) for rp in players if not rp.is_starter],
        })
    return {"teams": out}


def staleness_view(signals: Any) -> list[dict]:
    """Per-source freshness, straight off SignalBundle.availability."""
    if signals is None:
        return []
    return [
        {"name": a.name, "available": a.available, "age_seconds": a.age_seconds,
         "source": a.source, "note": a.note}
        for a in signals.availability
    ]


# ---------------------------------------------------------------- decisions

def _names_from_record(record: DecisionRecord) -> dict[str, str]:
    """player_id -> name, out of the snapshot the record itself carries."""
    snapshot = record.inputs_snapshot or {}
    return {
        str(p.get("id")): p.get("name", str(p.get("id")))
        for p in snapshot.get("roster", [])
        if p.get("id") is not None
    }


def decision_summary(record: DecisionRecord) -> dict:
    rec = record.recommendation or {}
    return {
        "id": str(record.id),
        "created_at": record.created_at,
        "week": record.week,
        "season": record.season,
        "type": record.decision_type.value,
        "confidence": record.confidence,
        "memo": record.memo,
        "human_response": record.human_response.value if record.human_response else None,
        "override_reason": record.override_reason,
        "abstained": bool(rec.get("abstained")),
        "truncated": bool(rec.get("truncated")),
        "starter_count": len(rec.get("starter_player_ids") or []),
    }


def decision_view(record: DecisionRecord, roster: Roster | None = None,
                  projections: dict[str, float] | None = None) -> dict:
    """The detail page. `roster` supplies live names; the record's own snapshot
    is the fallback, so an old decision still renders after a roster turnover."""
    rec = record.recommendation or {}
    effective = record.modified_recommendation or rec
    names = _names_from_record(record)
    if roster is not None:
        names.update({rp.player.platform_id: rp.player.name for rp in roster.players})
    projections = projections or {}

    starter_ids = effective.get("starter_player_ids") or []
    starters = [
        {"player_id": pid, "name": names.get(pid, pid),
         "projection": projections.get(pid)}
        for pid in starter_ids
    ]

    changes = []
    for c in rec.get("changes_from_current", []) or []:
        start_in = c.get("start_in_player_id")
        bench_out = c.get("bench_out_player_id")
        changes.append({
            "start_in": names.get(start_in, start_in),
            "bench_out": names.get(bench_out, bench_out) if bench_out else None,
            "reason": c.get("reason", ""),
        })

    # Every rostered player, so the modify form can offer the full choice set.
    choices = []
    if roster is not None:
        for rp in sorted(roster.players, key=_slot_rank):
            choices.append({
                "player_id": rp.player.platform_id,
                "name": rp.player.name,
                "position": rp.player.position.value.upper(),
                "slot": rp.slot.value.upper(),
                "projection": projections.get(rp.player.platform_id),
                "status": rp.player.status.value.lower(),
                "is_alert": rp.player.status.value.lower() in ALERT_STATUSES,
                # Locked players cannot be moved either way, so the form must
                # not invite a change ESPN would reject.
                "is_locked": rp.is_locked,
                "actual": rp.actual_points,
                "selected": rp.player.platform_id in starter_ids,
            })

    return {
        "summary": decision_summary(record),
        "record": record,
        "starters": starters,
        "changes": changes,
        "choices": choices,
        "locked_choices": [c for c in choices if c["is_locked"]],
        "staleness": record.signals_staleness or {},
        "what_would_change_this": rec.get("what_would_change_this"),
        "missing_information": rec.get("missing_information") or [],
        "is_modified": record.modified_recommendation is not None,
        "can_execute": bool(starter_ids) and not rec.get("abstained"),
    }


def plan_view(plan: Any) -> dict:
    """An ExecutionPlan, ready to show before the second gate."""
    return {
        "action_type": plan.action_type,
        "is_noop": plan.is_noop,
        "human_steps": list(plan.human_steps),
        "notes": list(plan.notes),
        "payload": plan.request_payload,
        "moves": [
            {"player_name": m.player_name,
             "from_slot": slot_name(m.from_slot),
             "to_slot": slot_name(m.to_slot)}
            for m in plan.moves
        ],
    }


def result_view(result: Any) -> dict:
    return {
        "success": result.success,
        "dry_run": result.dry_run,
        "executor": result.executor,
        "message": result.message,
        "error": result.error,
        "plan": plan_view(result.plan),
    }


# ------------------------------------------------------------------ trades

import time as _time  # local import keeps the top-of-file import block clean


def _epoch_now() -> float:
    """Epoch seconds — used by reads.py to timestamp a freshly-built value map."""
    return _time.time()


def _trade_player_row(
    player_id: str,
    names: dict,
    player_index: dict,
    value_map: dict,
    my_player_ids: set,
) -> dict:
    """Build a `player` dict for a trade package's send/receive list.

    Joins name, position, and nfl_team from the player index (all rosters).
    Falls back to the names map or the bare id when the index has no entry.
    AssetValue fields are None when no value map is available (degraded mode).
    """
    info = player_index.get(player_id)
    av = value_map.get(player_id) if value_map else None
    if info is not None:
        name = info["name"]
        position = info["position"].value.upper() if hasattr(info["position"], "value") else str(info["position"]).upper()
        nfl_team = info.get("team", "")
    else:
        name = names.get(player_id, player_id)
        position = ""
        nfl_team = ""
    return {
        "player_id": player_id,
        "name": name,
        "position": position,
        "nfl_team": _team_abbr(nfl_team) if nfl_team else "",
        # `unranked` means FantasyCalc has no price for them, which is not the
        # same as a price of zero, so it renders blank rather than 0.
        "value": None if (av is None or av.source == "unranked") else av.value,
        "value_source": av.source if av else "",
        "value_note": av.note if av else "",
        "is_mine": player_id in my_player_ids,
    }


def _build_package(
    raw: dict,
    index: int,
    names: dict,
    player_index: dict,
    value_map: dict,
    my_player_ids: set,
    standings_map: dict,
    has_values: bool,
    refused_because: str | None = None,
    my_players=None,
    projections: dict | None = None,
    settings=None,
) -> dict:
    """Assemble one package dict from a raw recommendation entry.

    All analytic quantities (ev_delta, fairness, verdict, lineup impact) are
    computed from `core.trade_value` — never parsed from strings or hard-coded.
    When `has_values` is False every value field is left None.
    """
    cid = str(raw.get("counterparty_team_id", ""))
    standing = standings_map.get(cid)
    counterparty_name = (standing.team_name if standing else
                         names.get(cid, f"Team {cid}"))
    # Standings record string (e.g. "3-1") and points-for
    if standing is not None:
        rec_str = f"{standing.wins}-{standing.losses}"
        if standing.ties:
            rec_str += f"-{standing.ties}"
        pf = standing.points_for
    else:
        rec_str = None
        pf = None

    # Resolve send/receive player ids, then resolve names.
    # `send_names`/`receive_names` are present on newer rows but absent on old ones.
    send_ids = raw.get("send_player_ids") or []
    receive_ids = raw.get("receive_player_ids") or []

    send = [_trade_player_row(pid, names, player_index, value_map, my_player_ids)
            for pid in send_ids]
    receive = [_trade_player_row(pid, names, player_index, value_map, my_player_ids)
               for pid in receive_ids]

    # Analytics — only when a value map is present. D-017: all numbers from core.
    ev_delta = None
    fairness = None
    verdict = None
    send_value = None
    receive_value = None
    lineup_delta = None
    lineup_before = None
    lineup_after = None

    if has_values and value_map:
        from fantasy_gm.core.trade_value import (
            evaluate_trade,
            evaluate_trade_for_roster,
        )

        # Prefer the roster-aware evaluation: value delta says whether the trade
        # is fair, but the starting-lineup delta is what decides whether it is
        # worth making, so compute it whenever the inputs are all present.
        incoming = [player_index[pid]["player"] for pid in receive_ids
                    if pid in player_index and player_index[pid].get("player") is not None]
        can_score_lineup = (
            my_players and projections and settings is not None
            and len(incoming) == len(receive_ids)
        )
        if can_score_lineup:
            try:
                ev = evaluate_trade_for_roster(
                    list(my_players), incoming, send_ids, receive_ids,
                    value_map, projections, settings,
                )
            except Exception:
                # A roster the optimizer cannot legally fill would otherwise take
                # the whole page down; the value comparison still stands.
                ev = evaluate_trade(send_ids, receive_ids, value_map)
        else:
            ev = evaluate_trade(send_ids, receive_ids, value_map)

        send_value = ev.send_value
        receive_value = ev.receive_value
        ev_delta = ev.ev_delta
        fairness = ev.fairness
        verdict = ev.verdict
        if ev.roster_impact is not None:
            lineup_before = ev.roster_impact.before_total
            lineup_after = ev.roster_impact.after_total
            lineup_delta = ev.roster_impact.delta

    # The other team's roster, so the ask can be sanity-checked in place. The
    # player index already carries `owner_team_id`, so this costs no extra read.
    counterparty_roster = []
    if cid:
        for pid, info in player_index.items():
            if str(info.get("owner_team_id") or "") != cid:
                continue
            counterparty_roster.append(
                _trade_player_row(pid, names, player_index, value_map, my_player_ids))
        counterparty_roster.sort(
            key=lambda r: (r["value"] is None, -(r["value"] or 0.0), r["name"]))

    # spine_pct: geometry only. 50.0 when unknown.
    if send_value is not None and receive_value is not None:
        total = send_value + receive_value
        spine_pct = (send_value / total * 100) if total > 0 else 50.0
    else:
        spine_pct = 50.0

    return {
        "index": index,
        "counterparty_team_id": cid,
        "counterparty_name": counterparty_name,
        "counterparty_record": rec_str,
        "counterparty_points_for": pf,
        "send": send,
        "receive": receive,
        "send_value": send_value,
        "receive_value": receive_value,
        "ev_delta": ev_delta,
        "fairness": fairness,
        "verdict": verdict,
        "lineup_delta": lineup_delta,
        "lineup_before": lineup_before,
        "lineup_after": lineup_after,
        "confidence": raw.get("confidence"),
        "rationale": raw.get("rationale") or "",
        "pitch": raw.get("counterparty_pitch") or "",
        "directive_violations": raw.get("directive_violations") or [],
        "refused_because": refused_because,
        "counterparty_roster": counterparty_roster,
        "spine_pct": round(spine_pct, 2),
    }


def trade_decision_view(
    record: DecisionRecord,
    *,
    names: dict,
    value_map: dict | None = None,
    my_players=None,
    league_players=None,
    projections=None,
    settings=None,
    standings=None,
    valued_at: float | None = None,
) -> dict:
    """The trade detail view — the only entry point the trades route should call.

    Branches on the four documented record shapes in order and degrades
    gracefully when any optional data (value_map, standings) is absent.

    D-017: analytics come from `core.trade_value`; this function only joins,
    labels, and orders. The one permitted arithmetic is `spine_pct` bar geometry.
    """
    rec = record.recommendation or {}
    has_values = bool(value_map)

    # Build fast-lookup structures.
    player_index = {}  # populated by caller if available; otherwise {}
    my_player_ids: set[str] = {
        str(p.platform_id) for p in (my_players or [])
    }
    standings_map: dict[str, Any] = {
        s.team_id: s for s in (standings or [])
    }
    # names already supplied by caller; player_index is passed through value_map
    # caller may pass a dict of pid -> info as `league_players`.
    if league_players and isinstance(league_players, dict):
        player_index = league_players
    elif league_players:
        # A bare list of Players carries no ownership, which the counterparty
        # roster and the incoming-player lookup both need. Fail loudly rather
        # than rendering a package with silently missing halves.
        raise TypeError(
            "league_players must be the player index (pid -> info dict) from "
            "reads.league_player_index, not a list of Player objects")

    # ---- shape detection (contract order) ----
    if "trades" in rec:
        shape = "packages"
    elif "truncated" in rec:
        shape = "truncated"
    elif "abstained" in rec:
        shape = "abstained"
    else:
        shape = "unknown"

    packages = []
    refused = []
    evaluated = []
    missing_information: list[str] = []
    what_you_would_need: str | None = None
    what_would_change_this: str | None = None
    selected_deterministically = False

    if shape == "packages":
        raw_trades: list[dict] = rec.get("trades") or []
        for i, raw in enumerate(raw_trades, 1):
            packages.append(_build_package(
                raw, i, names, player_index, value_map or {},
                my_player_ids, standings_map, has_values,
                my_players=my_players, projections=projections, settings=settings,
            ))
        for i, raw in enumerate(rec.get("refused_trades") or [], 1):
            refused.append(_build_package(
                raw, i, names, player_index, value_map or {},
                my_player_ids, standings_map, has_values,
                refused_because=raw.get("refused_because"),
                my_players=my_players, projections=projections, settings=settings,
            ))
        selected_deterministically = bool(rec.get("selected_deterministically"))
        what_would_change_this = rec.get("what_would_change_this")

    elif shape == "truncated":
        for raw in rec.get("evaluated_packages") or []:
            cid = str(raw.get("counterparty_team_id") or "")
            standing = standings_map.get(cid)
            cname = (standing.team_name if standing else
                     names.get(cid, f"Team {cid}"))
            send_ids = raw.get("send_player_ids") or []
            receive_ids = raw.get("receive_player_ids") or []
            evaluated.append({
                "counterparty_team_id": cid or None,
                "counterparty_name": cname,
                "send": [_trade_player_row(pid, names, player_index, value_map or {},
                                           my_player_ids) for pid in send_ids],
                "receive": [_trade_player_row(pid, names, player_index, value_map or {},
                                              my_player_ids) for pid in receive_ids],
                # Passed through verbatim — not parsed into columns (contract rule).
                "evaluation_text": raw.get("evaluation") or "",
            })

    elif shape == "abstained":
        missing_information = rec.get("missing_information") or []
        what_you_would_need = rec.get("what_you_would_need")
        what_would_change_this = rec.get("what_would_change_this")

    return {
        "summary": decision_summary(record),
        "shape": shape,
        "memo": record.memo or "",
        "packages": packages,
        "refused": refused,
        "evaluated": evaluated,
        "missing_information": missing_information,
        "what_you_would_need": what_you_would_need,
        "what_would_change_this": what_would_change_this,
        "selected_deterministically": selected_deterministically,
        "truncated": bool(rec.get("truncated")),
        "hit_step_limit": bool(rec.get("hit_step_limit")),
        "llm_calls": rec.get("llm_calls"),
        "llm_budget": rec.get("llm_budget"),
        "agent_text": rec.get("agent_text"),
        "valued_at": valued_at,
        "has_values": has_values,
    }


def _owner_label(info: dict, standings_names: dict) -> str:
    """Which fantasy team holds this player, named rather than numbered.

    ESPN's member records frequently carry no owner name at all, so the owning
    team is identified the way it is everywhere else on the site: from standings.
    """
    tid = str(info.get("owner_team_id") or "")
    named = standings_names.get(tid)
    if named:
        return named
    owner = (info.get("owner_name") or "").strip()
    if owner and owner.lower() != "unknown":
        return owner
    return f"Team {tid}" if tid else ""


def trade_brief_view(
    roster,
    value_map: dict,
    chips: list,
    league_players: dict,
    prefs=None,
    standings=None,
) -> dict:
    """Sidebar form inputs for starting a new trade run.

    Chip classification comes from `trade_chips`; sorting and selection marks
    from `TradePreferences`. No analytics invented here.
    """
    from fantasy_gm.models import Position

    standings_names = {st.team_id: st.team_name for st in (standings or [])}

    BRIEF_POSITIONS = [Position.QB, Position.RB, Position.WR, Position.TE]
    has_values = bool(value_map)

    chip_ids: set[str] = {rp.player.platform_id for rp, _ in chips}
    # `prefs` may be a TradePreferences or None.
    selected_positions: set[str] = set()
    selected_offerable: set[str] = set()
    selected_targets: set[str] = set()
    if prefs is not None:
        selected_positions = {p.value for p in (prefs.want_positions or [])}
        selected_offerable = set(prefs.offerable_ids or [])
        selected_targets = set(prefs.target_ids or [])

    positions = [
        {"value": p.value, "label": p.value,
         "selected": p.value in selected_positions}
        for p in BRIEF_POSITIONS
    ]

    my_team_id = roster.team_id if roster else None

    # Build offerable list: all my roster players, chips first, then value desc.
    offerable = []
    if roster:
        vm = value_map or {}
        for rp in roster.players:
            pid = rp.player.platform_id
            av = vm.get(pid)
            is_chip = pid in chip_ids
            # slot comes from the RosterPlayer's slot attribute.
            slot = rp.slot.value.upper() if hasattr(rp.slot, "value") else str(rp.slot).upper()
            offerable.append({
                "player_id": pid,
                "name": rp.player.name,
                "position": rp.player.position.value.upper(),
                "nfl_team": _team_abbr(rp.player.nfl_team),
                # `unranked` means FantasyCalc has no price for them, which is not the
        # same as a price of zero, so it renders blank rather than 0.
        "value": None if (av is None or av.source == "unranked") else av.value,
                "value_source": av.source if av else "",
                "value_note": av.note if av else "",
                "is_mine": True,
                "is_chip": is_chip,
                "is_starter": rp.is_starter,
                "slot": slot,
                "selected": pid in selected_offerable,
            })
        # Sort: chips first, then by value descending (None treated as 0).
        offerable.sort(key=lambda r: (not r["is_chip"], -(r["value"] or 0.0)))

    # Targets: other-team players from the league player index, value desc.
    targets = []
    for pid, info in (league_players or {}).items():
        if info.get("owner_team_id") == my_team_id:
            continue
        av = (value_map or {}).get(pid)
        targets.append({
            "player_id": pid,
            "name": info["name"],
            "position": (info["position"].value.upper()
                         if hasattr(info["position"], "value")
                         else str(info["position"]).upper()),
            "nfl_team": info.get("team", ""),
            "owner_team_name": _owner_label(info, standings_names),
            "owner_team_id": info.get("owner_team_id", ""),
            "owner_name": info.get("owner_name", ""),
            # `unranked` means FantasyCalc has no price for them, which is not the
        # same as a price of zero, so it renders blank rather than 0.
        "value": None if (av is None or av.source == "unranked") else av.value,
            "selected": pid in selected_targets,
        })
    targets.sort(key=lambda r: -(r["value"] or 0.0))

    return {
        "positions": positions,
        "offerable": offerable,
        "chip_count": len(chip_ids),
        "roster_count": len(offerable),
        "targets": targets,
        "notes": prefs.notes if prefs else "",
        "has_values": has_values,
    }


def trade_needs_view(my_needs: dict, chips: list) -> dict:
    """Right-rail needs/surplus table.

    State precedence (contract): need > thin > surplus(>0) > ok.
    `my_needs` is the raw dict from `TradeToolContext.roster_needs`.
    """
    rows = []
    for pos, info in my_needs.items():
        need = info.get("need", False)
        thin = info.get("thin", False)
        surplus = info.get("surplus", 0)
        if need:
            state = "need"
        elif thin:
            state = "thin"
        elif surplus > 0:
            state = "surplus"
        else:
            state = "ok"
        rows.append({
            "position": pos.value if hasattr(pos, "value") else str(pos),
            "state": state,
            "best": info.get("best", 0.0),
            "bar": info.get("bar", 0.0),
            "surplus": surplus,
            "unfilled": info.get("unfilled", 0),
        })
    chip_count = len(chips)
    return {"rows": rows, "chip_count": chip_count}


def trade_send_plan_view(plan) -> dict:
    """Render a `TradeSendPlan` for the confirmation/steps page."""
    return {
        "counterparty_team_id": plan.counterparty_team_id,
        "send_names": list(plan.send_names),
        "receive_names": list(plan.receive_names),
        "human_steps": list(plan.human_steps),
        "notes": list(plan.notes),
    }
