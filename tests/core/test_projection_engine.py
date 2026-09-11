"""Tests for the multi-source projection blender."""
import pytest

from fantasy_gm.core.projection_engine import blend_player, blend_projections


def test_mean_of_two_sources():
    bp = blend_player({"espn": 10.0, "sleeper": 14.0})
    assert bp.mean == pytest.approx(12.0)
    assert bp.n_sources == 2
    assert bp.floor < bp.mean < bp.ceiling


def test_agreeing_sources_narrower_than_disagreeing():
    agree = blend_player({"espn": 12.0, "sleeper": 12.0})
    disagree = blend_player({"espn": 5.0, "sleeper": 19.0})
    assert agree.mean == pytest.approx(12.0)
    assert disagree.mean == pytest.approx(12.0)
    # Wider source disagreement → wider floor/ceiling band.
    assert (disagree.ceiling - disagree.floor) > (agree.ceiling - agree.floor)


def test_weighted_blend():
    bp = blend_player({"espn": 10.0, "sleeper": 20.0}, weights={"espn": 3.0, "sleeper": 1.0})
    # weighted toward espn: (10*3 + 20*1)/4 = 12.5
    assert bp.mean == pytest.approx(12.5)


def test_single_source_still_bands():
    bp = blend_player({"espn": 10.0})
    assert bp.n_sources == 1
    assert bp.floor < 10.0 < bp.ceiling


def test_empty_is_zero():
    bp = blend_player({})
    assert bp.mean == 0.0 and bp.n_sources == 0


def test_floor_never_negative():
    bp = blend_player({"espn": 1.0, "sleeper": 1.0})
    assert bp.floor >= 0.0


def test_blend_projections_over_union_of_ids():
    sources = {
        "espn": {"p1": 10.0, "p2": 5.0},
        "sleeper": {"p1": 12.0, "p3": 8.0},
    }
    out = blend_projections(sources)
    assert set(out.keys()) == {"p1", "p2", "p3"}
    assert out["p1"].n_sources == 2
    assert out["p2"].n_sources == 1
    assert out["p3"].sources == ["sleeper"]
