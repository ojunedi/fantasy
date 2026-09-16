"""
Optional manager directives for a trade run.

The load-bearing property: an empty TradePreferences must change nothing, so
skipping the interview leaves the existing behaviour byte-for-byte identical.
"""
import pytest

from fantasy_gm.agent.trade.preferences import (
    TradePreferences,
    describe,
    resolve_players,
)
from fantasy_gm.memo.interview import interview_trade_preferences
from fantasy_gm.models import Position

_ROSTER = {"1": "Bijan Robinson", "2": "Baker Mayfield",
           "3": "Jameson Williams", "4": "Kyren Williams"}


def test_empty_preferences_are_inert():
    p = TradePreferences()
    assert p.is_empty()
    assert describe(p, _ROSTER) == ""
    assert p.violations(["1"], ["2"]) == []


def test_resolve_matches_by_partial_name():
    ids, problems = resolve_players("bijan, mayfield", _ROSTER)
    assert ids == ["1", "2"]
    assert problems == []


def test_resolve_reports_ambiguity_instead_of_guessing():
    ids, problems = resolve_players("williams", _ROSTER)
    assert ids == []
    assert len(problems) == 1 and "ambiguous" in problems[0]
    # An exact full-name match still resolves even though it is a substring of none.
    ids, problems = resolve_players("Kyren Williams", _ROSTER)
    assert ids == ["4"] and problems == []


def test_resolve_reports_unknown_name():
    ids, problems = resolve_players("Patrick Mahomes", _ROSTER)
    assert ids == []
    assert "no player matched" in problems[0]


def test_violation_flags_a_player_you_did_not_offer():
    p = TradePreferences(offerable_ids=["2"])
    problems = p.violations(send_ids=["1"], receive_ids=["9"], names=_ROSTER)
    assert len(problems) == 1
    assert "Bijan Robinson" in problems[0]          # resolved to a readable name
    # Sending only what was offered is clean.
    assert p.violations(send_ids=["2"], receive_ids=["9"], names=_ROSTER) == []


def test_violation_flags_a_missed_target():
    p = TradePreferences(target_ids=["7"])
    problems = p.violations(send_ids=["2"], receive_ids=["9"], names={"7": "Jonathan Taylor"})
    assert len(problems) == 1 and "Jonathan Taylor" in problems[0]
    assert p.violations(send_ids=["2"], receive_ids=["7"]) == []


def test_describe_renders_every_directive():
    p = TradePreferences(want_positions=[Position.RB], offerable_ids=["2"],
                         target_ids=["1"], notes="no rentals")
    text = describe(p, _ROSTER)
    assert "RB" in text
    assert "Baker Mayfield" in text      # offerable
    assert "Bijan Robinson" in text      # target
    assert "no rentals" in text


@pytest.mark.parametrize("answer,expected", [
    ("1,3,5", [0, 2, 4]),
    ("1-4", [0, 1, 2, 3]),
    ("2 4", [1, 3]),
    ("3,1", [2, 0]),        # order preserved as typed
    ("1,1,2", [0, 1]),      # de-duplicated
])
def test_parse_selection_accepts_numbers_and_ranges(answer, expected):
    from fantasy_gm.memo.interview import _parse_selection
    indices, problems = _parse_selection(answer, 6)
    assert indices == expected
    assert problems == []


@pytest.mark.parametrize("answer,marker", [
    ("99", "out of range"),
    ("abc", "not a number"),
    ("4-2", "not a valid range"),
])
def test_parse_selection_reports_bad_input(answer, marker):
    from fantasy_gm.memo.interview import _parse_selection
    indices, problems = _parse_selection(answer, 6)
    assert indices == []
    assert any(marker in p for p in problems)


def _roster_ctx():
    from fantasy_gm.models import Player, PlayerStatus, Roster, RosterPlayer

    def rp(pid, name, pos, starter):
        p = Player(platform_id=pid, name=name, position=pos,
                   eligible_positions=[pos], status=PlayerStatus.ACTIVE)
        return RosterPlayer(player=p, slot=pos, is_starter=starter)

    players = [rp("1", "Bijan Robinson", Position.RB, True),
               rp("2", "Baker Mayfield", Position.QB, False),
               rp("3", "Michael Wilson", Position.WR, False)]

    class _Ctx:
        team_id = "8"

        def roster(self):
            return Roster(team_id="8", team_name="T", owner_name="Me",
                          players=players, week=1, season=2026)

        def value_map(self):
            raise RuntimeError("offline")   # exercise the degraded path

        def trade_chips(self, roster):
            raise RuntimeError("offline")

        def player_index(self):
            raise RuntimeError("offline")

    return _Ctx()


def test_picker_selects_players_by_number(monkeypatch, capsys):
    replies = iter(["", "1,3", "", ""])
    monkeypatch.setattr("builtins.input", lambda *_: next(replies))
    prefs = interview_trade_preferences(_roster_ctx(), interactive=True)
    assert prefs.offerable_ids == ["1", "3"]
    out = capsys.readouterr().out
    assert "Bijan Robinson" in out and "Michael Wilson" in out


def test_picker_skips_on_blank(monkeypatch):
    replies = iter(["", "", "", ""])
    monkeypatch.setattr("builtins.input", lambda *_: next(replies))
    prefs = interview_trade_preferences(_roster_ctx(), interactive=True)
    assert prefs.offerable_ids == []
    assert prefs.is_empty()


def test_interview_is_skipped_without_a_tty():
    """A piped/CI run must not block on input."""
    prefs = interview_trade_preferences(ctx=None, interactive=False)
    assert prefs.is_empty()


def test_interview_accepts_blank_answers(monkeypatch, capsys):
    """Pressing Enter through every question yields no constraints."""
    monkeypatch.setattr("builtins.input", lambda *_: "")

    class _Ctx:
        team_id = "8"

        def roster(self):
            raise AssertionError("should not be needed for blank answers")

        def player_index(self):
            raise AssertionError("should not be needed for blank answers")

    prefs = interview_trade_preferences(_Ctx(), interactive=True)
    assert prefs.is_empty()
    assert "standard scan" in capsys.readouterr().out


@pytest.mark.parametrize("answer,expected", [("RB", [Position.RB]),
                                             ("rb wr", [Position.RB, Position.WR])])
def test_interview_parses_wanted_positions(monkeypatch, answer, expected):
    replies = iter([answer, "", "", ""])
    monkeypatch.setattr("builtins.input", lambda *_: next(replies))

    class _Ctx:
        team_id = "8"

        def roster(self):
            raise RuntimeError("unavailable")   # exercised the guarded path

        def player_index(self):
            raise RuntimeError("unavailable")

    prefs = interview_trade_preferences(_Ctx(), interactive=True)
    assert prefs.want_positions == expected


# ---- The offer list is a HARD constraint ---------------------------------

def test_forbidden_sends_is_empty_when_unconstrained():
    assert TradePreferences().forbidden_sends(["1", "2"]) == []


def test_forbidden_sends_names_only_the_players_withheld():
    p = TradePreferences(offerable_ids=["2", "3"])
    assert p.forbidden_sends(["2", "3"]) == []
    assert p.forbidden_sends(["1", "2", "4"]) == ["1", "4"]


def test_a_missed_target_is_not_a_hard_block():
    """Which of MY players may leave is the manager's call; which player comes
    back is a preference the agent may miss and still be useful."""
    p = TradePreferences(target_ids=["9"], offerable_ids=["2"])
    assert p.forbidden_sends(["2"]) == []          # legal send
    assert p.violations(["2"], ["7"]) != []        # ...but flagged as a miss
