"""Worked-by-hand scenario (4 teams, QB/RB/WR dedicated + 1 FLEX(RB/WR/TE)):

Dedicated starters: QB=4, RB=4, WR=4 (num_teams * count).
FLEX pool after removing dedicated starters, sorted desc:
  TE 90, RB 80, WR 75, RB 70, WR 65, RB 60, WR 55, TE 50, TE 40, TE 30
Top 4 of that pool: TE 90, RB 80, WR 75, RB 70 -> tally RB+2, WR+1, TE+1.

Effective starters: QB=4, RB=6, WR=5, TE=1.
VOLS (value at the effective-starter rank): QB=70, RB=70, WR=75, TE=90.
VORP (rank + bench_offset {QB:1, RB:2, WR:2, TE:1}):
  QB rank5 -> 60, RB rank8 (clamped to last, rank7) -> 60, WR rank7 -> 55, TE rank2 -> 50.
"""
import pytest

from data.models import Position
from engine.replacement import compute_effective_starters, compute_replacement_baselines


def test_effective_starters_allocates_flex_by_best_remaining_value(test_league, sample_player_values):
    starters = compute_effective_starters(sample_player_values, test_league)

    assert starters[Position.QB] == 4
    assert starters[Position.RB] == 6
    assert starters[Position.WR] == 5
    assert starters[Position.TE] == 1


def test_replacement_baselines_vols_and_vorp(test_league, sample_player_values):
    baselines = compute_replacement_baselines(sample_player_values, test_league)

    assert baselines[Position.QB]["VOLS"] == pytest.approx(70)
    assert baselines[Position.RB]["VOLS"] == pytest.approx(70)
    assert baselines[Position.WR]["VOLS"] == pytest.approx(75)
    assert baselines[Position.TE]["VOLS"] == pytest.approx(90)

    assert baselines[Position.QB]["VORP"] == pytest.approx(60)
    assert baselines[Position.RB]["VORP"] == pytest.approx(60)
    assert baselines[Position.WR]["VORP"] == pytest.approx(55)
    assert baselines[Position.TE]["VORP"] == pytest.approx(50)


def test_baselines_clamp_gracefully_when_pool_is_small(test_league):
    from engine.replacement import PlayerValue

    tiny_pool = [
        PlayerValue(player_id="qb0", position=Position.QB, value=100),
    ]
    baselines = compute_replacement_baselines(tiny_pool, test_league)
    assert baselines[Position.QB]["VOLS"] == pytest.approx(100)
    assert baselines[Position.QB]["VORP"] == pytest.approx(100)


def test_zero_demand_position_gets_zero_baseline(test_league):
    """K has no dedicated slot and isn't FLEX-eligible in test_league.yaml, so it
    has zero roster demand -- the baseline should be 0.0, not the #1 K's value.
    (Uses a league clone with no K bench_offset, since a nonzero offset would
    itself push VORP's rank above zero -- a real league wouldn't configure a
    bench_offset for a position nobody rosters.)"""
    import dataclasses

    from engine.replacement import PlayerValue

    league = dataclasses.replace(
        test_league, bench_offsets={k: v for k, v in test_league.bench_offsets.items() if k != Position.K}
    )
    kickers = [
        PlayerValue(player_id="k0", position=Position.K, value=150),
        PlayerValue(player_id="k1", position=Position.K, value=120),
    ]
    baselines = compute_replacement_baselines(kickers, league)
    assert baselines[Position.K]["VOLS"] == pytest.approx(0.0)
    assert baselines[Position.K]["VORP"] == pytest.approx(0.0)
