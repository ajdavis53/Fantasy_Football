import pytest

from data.models import PlayerRanking, Position
from engine.replacement import PlayerValue
from engine.tiers import compute_gap_tiers, tiers_from_rankings


def _ranking(player_id, tier):
    return PlayerRanking(player_id=player_id, source="ETR", rank=1, tier=tier, position=Position.RB)


def test_tiers_from_rankings_returns_source_tiers_when_complete():
    rankings = [_ranking("a", 1), _ranking("b", 1), _ranking("c", 2)]
    assert tiers_from_rankings(rankings) == {"a": 1, "b": 1, "c": 2}


def test_tiers_from_rankings_returns_none_when_incomplete():
    rankings = [_ranking("a", 1), _ranking("b", None)]
    assert tiers_from_rankings(rankings) is None


def test_compute_gap_tiers_breaks_on_large_normalized_gaps():
    values = [100, 95, 90, 50, 45, 40, 10, 8, 5]
    player_values = [
        PlayerValue(player_id=f"p{i}", position=Position.RB, value=v) for i, v in enumerate(values)
    ]

    tiers = compute_gap_tiers(player_values, z_cutoff=1.0)

    assert tiers == {
        "p0": 1, "p1": 1, "p2": 1,
        "p3": 2, "p4": 2, "p5": 2,
        "p6": 3, "p7": 3, "p8": 3,
    }


def test_compute_gap_tiers_single_tier_for_small_positions():
    player_values = [
        PlayerValue(player_id="k0", position=Position.K, value=100),
        PlayerValue(player_id="k1", position=Position.K, value=50),
    ]
    tiers = compute_gap_tiers(player_values)
    assert tiers == {"k0": 1, "k1": 1}


def test_compute_gap_tiers_does_not_split_near_identical_values():
    """Near-tied players produce tiny, noisy gaps whose own stdev is tiny too;
    without an absolute floor, z-scores on that noise would spuriously split
    them into separate tiers."""
    values = [100.0, 99.9999999, 99.9999998, 99.9999997, 99.9999996]
    player_values = [
        PlayerValue(player_id=f"p{i}", position=Position.WR, value=v) for i, v in enumerate(values)
    ]
    tiers = compute_gap_tiers(player_values)
    assert len(set(tiers.values())) == 1
