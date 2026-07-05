"""Value-based drafting scores: a player's value over a replacement baseline."""
from __future__ import annotations

from data.models import LeagueSettings
from engine.replacement import PlayerValue, compute_replacement_baselines


_VALID_BASELINES = ("VORP", "VOLS")


def compute_vbd(
    player_values: list[PlayerValue], league: LeagueSettings, baseline: str = "VORP"
) -> dict[str, float]:
    """player_id -> (value - positional replacement baseline), for `baseline` in {"VORP", "VOLS"}."""
    if baseline not in _VALID_BASELINES:
        raise ValueError(f"baseline must be one of {_VALID_BASELINES}, got {baseline!r}")
    baselines = compute_replacement_baselines(player_values, league)
    return {
        pv.player_id: pv.value - baselines.get(pv.position, {}).get(baseline, 0.0)
        for pv in player_values
    }
