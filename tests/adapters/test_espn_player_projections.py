"""
get_player_projections returns correct positions, not a hardcoded WR.

Stubs _fetch to return a minimal kona_player_info payload with a QB and a RB,
verifies the method maps defaultPositionId → Position correctly and populates
player_name from fullName.
"""
import types
from unittest.mock import patch

import pytest

from fantasy_gm.adapters.espn import ESPNAdapter, ESPN_POSITION_MAP
from fantasy_gm.models import Position


def _stub_payload(week: int, season: int):
    """Minimal kona_player_info response with one QB and one RB."""
    return {
        "players": [
            {
                "player": {
                    "id": 1001,
                    "fullName": "Test QB",
                    "defaultPositionId": 1,  # QB in ESPN_POSITION_MAP
                    "stats": [
                        {
                            "statSourceId": 1,
                            "scoringPeriodId": week,
                            "seasonId": season,
                            "appliedTotal": 24.5,
                        }
                    ],
                }
            },
            {
                "player": {
                    "id": 1002,
                    "fullName": "Test RB",
                    "defaultPositionId": 2,  # RB in ESPN_POSITION_MAP
                    "stats": [
                        {
                            "statSourceId": 1,
                            "scoringPeriodId": week,
                            "seasonId": season,
                            "appliedTotal": 18.0,
                        }
                    ],
                }
            },
            {
                # Player with no matching projection week — must be excluded
                "player": {
                    "id": 1003,
                    "fullName": "No Proj",
                    "defaultPositionId": 3,  # WR
                    "stats": [
                        {
                            "statSourceId": 1,
                            "scoringPeriodId": week + 1,  # wrong week
                            "seasonId": season,
                            "appliedTotal": 9.0,
                        }
                    ],
                }
            },
        ]
    }


def test_player_projections_positions():
    adapter = ESPNAdapter.__new__(ESPNAdapter)

    with patch.object(ESPNAdapter, "_fetch", return_value=_stub_payload(3, 2026)):
        results = adapter.get_player_projections(week=3, season=2026)

    by_id = {r.player_id: r for r in results}

    assert set(by_id.keys()) == {"1001", "1002"}, "player 1003 has no matching week, must be excluded"

    qb = by_id["1001"]
    assert qb.position == Position.QB
    assert qb.player_name == "Test QB"
    assert qb.projected_points == 24.5
    assert qb.week == 3
    assert qb.season == 2026

    rb = by_id["1002"]
    assert rb.position == Position.RB
    assert rb.player_name == "Test RB"
    assert rb.projected_points == 18.0
