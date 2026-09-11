"""
Deterministic PPR scoring calculator.

Translates raw stat lines into fantasy points using the exact rules
from LeagueSettings. No LLM, no estimation — pure arithmetic.

ESPN stat IDs used as keys (the platform adapter normalizes to these).
"""
from __future__ import annotations

from fantasy_gm.models import ScoringRules

# Standard ESPN stat IDs → human name mapping (for tests and debugging)
STAT_NAMES: dict[str, str] = {
    "3": "pass_yards",
    "4": "pass_td",
    "20": "pass_int",
    "24": "rush_yards",
    "25": "rush_td",
    "41": "rec_yards",
    "42": "rec_td",
    "53": "reception",      # PPR stat
    "72": "fumble_lost",
    "74": "2pt_conversion",
}


def calculate_score(stats: dict[str, float], rules: ScoringRules) -> float:
    """
    Compute fantasy points for a stat line given league scoring rules.

    Args:
        stats: Map of stat_id (str) -> stat value (float).
        rules: League-specific ScoringRules.

    Returns:
        Total fantasy points as float.
    """
    total = 0.0
    for stat_id, value in stats.items():
        pts_per_unit = rules.get(stat_id)
        total += value * pts_per_unit
    return round(total, 2)


def ppr_rules() -> ScoringRules:
    """Return a standard PPR scoring ruleset for testing and default use."""
    from fantasy_gm.models import ScoringRule
    return ScoringRules(rules=[
        ScoringRule(stat="3", points=0.04),     # pass yards (1 per 25)
        ScoringRule(stat="4", points=4.0),      # pass TD
        ScoringRule(stat="20", points=-2.0),    # INT
        ScoringRule(stat="24", points=0.1),     # rush yards (1 per 10)
        ScoringRule(stat="25", points=6.0),     # rush TD
        ScoringRule(stat="41", points=0.1),     # rec yards (1 per 10)
        ScoringRule(stat="42", points=6.0),     # rec TD
        ScoringRule(stat="53", points=1.0),     # reception (PPR)
        ScoringRule(stat="72", points=-2.0),    # fumble lost
        ScoringRule(stat="74", points=2.0),     # 2pt conversion
    ])
