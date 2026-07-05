"""Turn raw stat projections into league-specific fantasy points.

Only needed when a source gives raw stats (e.g. nfl_data_py-derived
projections) rather than already-scored points. ETR's CSV rankings are
typically pre-scored for a scoring format and can bypass this module.
"""
from __future__ import annotations

from data.models import ScoringRules


def score_players(
    stat_projections: dict[str, dict[str, float]], rules: ScoringRules
) -> dict[str, float]:
    """Map player_id -> raw stat dict into player_id -> fantasy points."""
    return {player_id: rules.points_for(stats) for player_id, stats in stat_projections.items()}
