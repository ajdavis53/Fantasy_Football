import pandas as pd
import pytest

from data.models import PlayerRanking, Position, ScoringRules
from data.projections import (
    _curve_value,
    _smooth,
    fit_positional_curves,
    project_points,
    score_historical,
)


def _ranking(player_id, position, rank, pos_rank=None, projected_points=None):
    return PlayerRanking(
        player_id=player_id,
        source="ETR",
        rank=rank,
        tier=None,
        position=position,
        projected_points=projected_points,
        pos_rank=pos_rank,
    )


def test_score_historical_applies_scoring_rules():
    df = pd.DataFrame(
        {
            "receptions": [100.0, 50.0],
            "receiving_yards": [1000.0, 500.0],
            "receiving_tds": [10.0, 5.0],
        }
    )
    ppr = ScoringRules(points_per_stat={"rec": 1.0, "rec_yd": 0.1, "rec_td": 6.0})
    half = ScoringRules(points_per_stat={"rec": 0.5, "rec_yd": 0.1, "rec_td": 6.0})

    assert score_historical(df, ppr).tolist() == pytest.approx([260.0, 130.0])
    assert score_historical(df, half).tolist() == pytest.approx([210.0, 105.0])


def test_score_historical_sums_multi_column_stats():
    df = pd.DataFrame(
        {
            "rushing_fumbles_lost": [1.0],
            "receiving_fumbles_lost": [2.0],
            "sack_fumbles_lost": [1.0],
        }
    )
    rules = ScoringRules(points_per_stat={"fumble_lost": -2.0})
    assert score_historical(df, rules).tolist() == pytest.approx([-8.0])


def test_score_historical_ignores_unmapped_and_missing_columns():
    df = pd.DataFrame({"receptions": [10.0]})
    rules = ScoringRules(points_per_stat={"rec": 1.0, "rush_yd": 0.1, "not_a_stat": 5.0})
    assert score_historical(df, rules).tolist() == pytest.approx([10.0])


def test_smooth_damps_an_inflated_peak():
    curve = [500.0, 300.0, 290.0, 280.0, 270.0]
    smoothed = _smooth(curve, window=5)
    assert smoothed[0] < curve[0]
    assert len(smoothed) == len(curve)


def test_smooth_window_of_one_is_identity():
    curve = [10.0, 8.0, 6.0]
    assert _smooth(curve, window=1) == curve


def test_curve_value_is_one_indexed_and_clamps():
    curve = [100.0, 90.0, 80.0]
    assert _curve_value(curve, 1) == 100.0
    assert _curve_value(curve, 3) == 80.0
    assert _curve_value(curve, 99) == 80.0
    assert _curve_value(curve, 0) == 100.0
    assert _curve_value([], 1) == 0.0


def test_project_points_reads_positional_rank_off_the_curve():
    curves = {Position.RB: [300.0, 250.0, 200.0]}
    rankings = [
        _ranking("rb1", Position.RB, rank=1, pos_rank=1),
        _ranking("rb3", Position.RB, rank=5, pos_rank=3),
    ]
    points = project_points(rankings, curves)
    assert points["rb1"] == 300.0
    assert points["rb3"] == 200.0


def test_project_points_preserves_supplied_projections():
    """A real projections export should win over the fitted curve."""
    curves = {Position.RB: [300.0, 250.0]}
    rankings = [_ranking("rb1", Position.RB, rank=1, pos_rank=1, projected_points=123.4)]
    assert project_points(rankings, curves)["rb1"] == 123.4


def test_project_points_derives_positional_rank_when_absent():
    curves = {Position.WR: [400.0, 350.0, 300.0]}
    rankings = [
        _ranking("wr_b", Position.WR, rank=10),
        _ranking("wr_a", Position.WR, rank=2),
    ]
    points = project_points(rankings, curves)
    assert points["wr_a"] == 400.0
    assert points["wr_b"] == 350.0


def test_project_points_handles_position_missing_from_curves():
    rankings = [_ranking("k1", Position.K, rank=200, pos_rank=1)]
    assert project_points(rankings, {})["k1"] == 0.0


def test_fitted_curves_are_non_increasing_and_cover_all_positions():
    """Uses the on-disk cache written by an earlier real fit when present, so this
    stays an offline unit test; skipped when no cache and no network."""
    rules = ScoringRules(points_per_stat={"rec": 1.0, "rec_yd": 0.1, "rec_td": 6.0})
    try:
        curves = fit_positional_curves(rules, seasons=(2022, 2023, 2024))
    except Exception as exc:  # pragma: no cover - depends on network/cache
        pytest.skip(f"historical data unavailable: {exc}")

    for position in (Position.QB, Position.RB, Position.WR, Position.TE, Position.K, Position.DEF):
        curve = curves[position]
        assert curve, f"{position} curve is empty"
        assert curve == sorted(curve, reverse=True), f"{position} curve is not non-increasing"
