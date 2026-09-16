"""
Tolerant list arguments in LLM tool schemas.

Models send a JSON-encoded string where a list is declared often enough to
matter: 29% of tool calls in one live trade run failed on exactly this, wasting
turns until the run could not converge. These tests pin the coercion AND the
guarantee that the schema still advertises an array, so we accept the mistake
without teaching the model to make it.
"""
import pytest
from pydantic import BaseModel, ValidationError

from fantasy_gm.agent.lc_tools import ProposeLineupArgs
from fantasy_gm.agent.schema import StrList, coerce_str_list, dict_list
from fantasy_gm.agent.trade.lc_tools import (
    EvaluateTradeArgs,
    PlayerIdsArgs,
    ProposeTradesArgs,
)


class _Item(BaseModel):
    a: str


class _Model(BaseModel):
    ids: StrList
    items: dict_list(_Item) = []


# ---- The live failure ----------------------------------------------------

def test_the_exact_payload_that_failed_live_now_validates():
    args = EvaluateTradeArgs(send_player_ids='["4360761", "4696044"]',
                             receive_player_ids='["4431452"]',
                             counterparty_team_id="2")
    assert args.send_player_ids == ["4360761", "4696044"]
    assert args.receive_player_ids == ["4431452"]


def test_schema_still_advertises_an_array():
    """We tolerate the string; we must not invite it."""
    for model, field in [(EvaluateTradeArgs, "send_player_ids"),
                         (PlayerIdsArgs, "player_ids"),
                         (ProposeTradesArgs, "trades"),
                         (ProposeLineupArgs, "starter_player_ids"),
                         (ProposeLineupArgs, "changes_from_current")]:
        prop = model.model_json_schema()["properties"][field]
        assert prop["type"] == "array", f"{model.__name__}.{field} is no longer an array"


# ---- String coercion -----------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ('["1", "2"]', ["1", "2"]),          # JSON array as a string
    ("[1, 2]", ["1", "2"]),              # JSON array of numbers
    ("1,2, 3", ["1", "2", "3"]),         # comma-separated
    ("solo", ["solo"]),                  # bare scalar string
    ("", []),                            # empty string
    (["1", "2"], ["1", "2"]),            # already correct — untouched
    (['["1", "2"]'], ["1", "2"]),        # list wrapping a stringified list
    (7, ["7"]),                          # bare number
    ([1, 2], ["1", "2"]),                # list of numbers
])
def test_coerce_str_list_normalises_what_models_actually_send(value, expected):
    assert coerce_str_list(value) == expected


def test_coercion_applies_through_the_model():
    m = _Model(ids='["a", "b"]')
    assert m.ids == ["a", "b"]


def test_a_single_object_is_accepted_where_a_list_was_declared():
    m = _Model(ids=[], items={"a": "x"})
    assert m.items == [_Item(a="x")]


def test_a_json_string_of_objects_is_accepted():
    m = _Model(ids=[], items='[{"a": "x"}, {"a": "y"}]')
    assert [i.a for i in m.items] == ["x", "y"]


def test_propose_trades_accepts_a_stringified_package_list():
    pkg = ('[{"counterparty_team_id": "3", "send_player_ids": "[\\"1\\"]", '
           '"receive_player_ids": ["2"], "rationale": "r", '
           '"counterparty_pitch": "p", "confidence": 0.5}]')
    args = ProposeTradesArgs(trades=pkg, memo="m", what_would_change_this="w")
    assert args.trades[0].send_player_ids == ["1"]   # nested coercion too
    assert args.trades[0].receive_player_ids == ["2"]


# ---- What we deliberately do NOT guess -----------------------------------

def test_a_renamed_field_is_still_an_error():
    """Coercing a wrong *value* is safe; inventing a missing argument is not."""
    with pytest.raises(ValidationError):
        PlayerIdsArgs(position="QB")


def test_unparseable_object_soup_is_left_to_fail():
    with pytest.raises(ValidationError):
        _Model(ids=[], items="not json at all")
