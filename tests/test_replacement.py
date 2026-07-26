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


def test_positions_with_demand_ignores_bench(test_league):
    """test_league.yaml starts QB/RB/WR + a RB/WR/TE flex, and benches anything.
    A position only the bench accepts is not real demand."""
    from engine.replacement import positions_with_demand

    demand = positions_with_demand(test_league)
    assert demand == frozenset({Position.QB, Position.RB, Position.WR, Position.TE})
    assert Position.K not in demand
    assert Position.DEF not in demand


def test_unstartable_positions_are_filtered_out(test_league):
    """A league with no kicker slot must not surface kickers at all. Left in,
    they get a zero baseline, bank their whole projection as value over
    replacement, and outrank real picks."""
    from engine.replacement import PlayerValue, filter_to_rosterable

    values = [
        PlayerValue(player_id="rb0", position=Position.RB, value=250),
        PlayerValue(player_id="k0", position=Position.K, value=150),
        PlayerValue(player_id="def0", position=Position.DEF, value=140),
    ]
    kept = filter_to_rosterable(values, test_league)
    assert [pv.player_id for pv in kept] == ["rb0"]
