"""Positional tiers: prefer a ranking source's own tiers, else detect gaps."""
from __future__ import annotations

import statistics

from data.models import PlayerRanking
from engine.replacement import PlayerValue


def tiers_from_rankings(rankings: list[PlayerRanking]) -> dict[str, int] | None:
    """Use a source's own tier column (e.g. ETR's) if every ranking has one."""
    if not rankings or any(r.tier is None for r in rankings):
        return None
    return {r.player_id: r.tier for r in rankings}


def compute_gap_tiers(
    player_values: list[PlayerValue], z_cutoff: float = 1.0, min_gap: float = 0.5
) -> dict[str, int]:
    """Assign tiers per position from normalized point-gaps between consecutive players.

    A new tier starts whenever the gap to the next-best player, normalized by
    that position's average gap, exceeds `z_cutoff` -- but never for a gap
    smaller than `min_gap` points, regardless of z-score. That floor matters
    when several players have near-identical values: their gaps' own stdev
    is then tiny, which would otherwise amplify meaningless noise into
    spurious tier breaks among effectively-tied players. Positions with three
    or fewer players (too few gaps for a meaningful average) get a single tier.
    """
    by_position: dict[str, list[PlayerValue]] = {}
    for pv in player_values:
        by_position.setdefault(pv.position.value, []).append(pv)

    tiers: dict[str, int] = {}
    for players in by_position.values():
        players_sorted = sorted(players, key=lambda pv: pv.value, reverse=True)
        gaps = [
            players_sorted[i].value - players_sorted[i + 1].value
            for i in range(len(players_sorted) - 1)
        ]

        if len(gaps) < 3:
            for pv in players_sorted:
                tiers[pv.player_id] = 1
            continue

        mean_gap = statistics.mean(gaps)
        stdev_gap = statistics.pstdev(gaps) or 1e-9

        tier = 1
        tiers[players_sorted[0].player_id] = tier
        for i, gap in enumerate(gaps):
            if gap >= min_gap and (gap - mean_gap) / stdev_gap > z_cutoff:
                tier += 1
            tiers[players_sorted[i + 1].player_id] = tier

    return tiers
