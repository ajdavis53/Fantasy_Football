"""Turn ETR's ranks into projected fantasy points.

ETR's Top-300 export gives an ordering (rank, positional rank, ADP) but no
projected point totals, and value-based drafting is a *points* differential:
"rank 12 minus rank 30" is meaningless, whereas "18.4 points above the last
startable RB" is the whole point. This module supplies the missing points.

The approach: fit a points-by-positional-rank curve from what players
actually scored in recent seasons -- the QB1 finished with X, the QB2 with
Y, and so on -- then read ETR's ranks off that curve. The curve is fitted
under *this league's* scoring rules (via `engine.scoring`), so a full-PPR
league and a standard league get differently-shaped curves from the same
historical stats. ETR supplies the opinion (who is better); history supplies
the shape (how much better).

If ETR's separate projections product is ever exported, prefer it: pass
those points through `PlayerRanking.projected_points` and skip this module
entirely. `project_points` already keeps any points already present.
"""
from __future__ import annotations

import statistics
from pathlib import Path

import pandas as pd

from data.models import PlayerRanking, Position, ScoringRules

CACHE_DIR = Path(__file__).parent / "cache"
# Four seasons so the fit still rests on three if the most recent one has not
# been published by nflverse yet; it is picked up automatically once it is.
DEFAULT_SEASONS = (2022, 2023, 2024, 2025)

# ScoringRules stat key -> nfl_data_py seasonal column(s), summed when several.
STAT_COLUMN_MAP: dict[str, tuple[str, ...]] = {
    "pass_yd": ("passing_yards",),
    "pass_td": ("passing_tds",),
    "pass_int": ("interceptions",),
    "rush_yd": ("rushing_yards",),
    "rush_td": ("rushing_tds",),
    "rec": ("receptions",),
    "rec_yd": ("receiving_yards",),
    "rec_td": ("receiving_tds",),
    "fumble_lost": ("rushing_fumbles_lost", "receiving_fumbles_lost", "sack_fumbles_lost"),
}

# Positions nfl_data_py's seasonal data covers (it is built from offensive
# play-by-play, so kickers and team defenses are absent).
FITTABLE_POSITIONS = (Position.QB, Position.RB, Position.WR, Position.TE)

# K and DST are effectively interchangeable in fantasy -- the gap between the
# best and the 12th-best is small enough that VBD should land near zero and
# keep them out of early rounds. A shallow linear decline reproduces that
# without needing a separate data source. (top_points, decline_per_rank)
FALLBACK_CURVE_PARAMS: dict[Position, tuple[float, float]] = {
    Position.K: (150.0, 2.5),
    Position.DEF: (140.0, 3.0),
}
FALLBACK_CURVE_LENGTH = 40


class ProjectionError(RuntimeError):
    pass


def _fetch_seasonal_with_positions(seasons: tuple[int, ...]) -> pd.DataFrame:
    """Seasonal stat totals joined to each player's position, cached to disk.

    Seasons are fetched individually and any that nflverse has not published
    yet are skipped with a warning, rather than failing the whole fit -- the
    most recent season only appears some months after it ends, so a hard
    requirement would break the tool for part of every year.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"seasonal_{'_'.join(str(s) for s in seasons)}.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path)

    import nfl_data_py as nfl

    frames = []
    missing = []
    for season in seasons:
        try:
            frames.append(nfl.import_seasonal_data([season]))
        except Exception:
            missing.append(season)

    if not frames:
        raise ProjectionError(
            f"none of the seasons {seasons} could be fetched; check network access to nflverse"
        )
    if missing:
        print(f"warning: no nflverse data yet for {missing}; fitting curves on {[s for s in seasons if s not in missing]}")

    seasonal = pd.concat(frames, ignore_index=True)
    ids = nfl.import_ids()[["gsis_id", "position"]].dropna(subset=["gsis_id"])
    merged = seasonal.merge(ids, left_on="player_id", right_on="gsis_id", how="left")
    merged.to_parquet(cache_path)
    return merged


def score_historical(df: pd.DataFrame, scoring: ScoringRules) -> pd.Series:
    """Apply league scoring rules to historical stat columns -> points per row."""
    points = pd.Series(0.0, index=df.index)
    for stat_key, value_per_unit in scoring.points_per_stat.items():
        for column in STAT_COLUMN_MAP.get(stat_key, ()):
            if column in df.columns:
                points = points + df[column].fillna(0) * value_per_unit
    return points


def _fallback_curve(position: Position) -> list[float]:
    top, decline = FALLBACK_CURVE_PARAMS[position]
    return [max(0.0, top - decline * i) for i in range(FALLBACK_CURVE_LENGTH)]


def _smooth(curve: list[float], window: int) -> list[float]:
    """Centered rolling mean, to damp ex-post order-statistic inflation.

    A raw rank curve is built from what the season's *actual* finishers
    scored, so its top entry is the luckiest, healthiest outcome anyone
    achieved -- systematically higher than what a player projected at that
    rank should be expected to score. Averaging each rank with its
    neighbours pulls those extremes back toward expectation. Without this,
    VBD badly overrates the top of steep positions (most visibly QB in
    one-QB leagues, where it can rate the QB1 several rounds above where
    both ETR and the market place him).
    """
    if window <= 1:
        return list(curve)
    half = window // 2
    return [
        statistics.fmean(curve[max(0, i - half) : min(len(curve), i + half + 1)])
        for i in range(len(curve))
    ]


def fit_positional_curves(
    scoring: ScoringRules,
    seasons: tuple[int, ...] = DEFAULT_SEASONS,
    smoothing_window: int = 5,
) -> dict[Position, list[float]]:
    """Points a player at each positional rank historically finished with.

    Returns position -> list where index i holds the points for positional
    rank i+1, taking the median across seasons (robust to a single outlier
    year), smoothing to damp ex-post inflation (see `_smooth`), and enforcing
    a non-increasing curve so rank order and value order never disagree.
    """
    df = _fetch_seasonal_with_positions(seasons)
    df = df.assign(points=score_historical(df, scoring))

    curves: dict[Position, list[float]] = {}
    for position in FITTABLE_POSITIONS:
        per_season: list[list[float]] = []
        for season in seasons:
            season_points = (
                df[(df["season"] == season) & (df["position"] == position.value)]["points"]
                .sort_values(ascending=False)
                .tolist()
            )
            if season_points:
                per_season.append(season_points)

        if not per_season:
            raise ProjectionError(
                f"no historical data for {position.value} in seasons {seasons}; cannot fit a curve"
            )

        length = max(len(s) for s in per_season)
        curve = [
            statistics.median([s[rank] for s in per_season if rank < len(s)])
            for rank in range(length)
        ]
        curve = _smooth(curve, window=smoothing_window)

        # Enforce non-increasing: median and smoothing can invert adjacent ranks.
        for i in range(1, len(curve)):
            curve[i] = min(curve[i], curve[i - 1])
        curves[position] = curve

    for position in FALLBACK_CURVE_PARAMS:
        curves[position] = _fallback_curve(position)

    return curves


def _curve_value(curve: list[float], rank: int) -> float:
    """Points at 1-indexed `rank`, clamping past the end of the curve to its tail."""
    if not curve:
        return 0.0
    return curve[min(max(rank, 1) - 1, len(curve) - 1)]


def project_points(
    rankings: list[PlayerRanking],
    curves: dict[Position, list[float]],
) -> dict[str, float]:
    """player_id -> projected points, from each player's positional rank.

    A ranking that already carries `projected_points` (e.g. from a real
    projections export) keeps that value rather than being overwritten.
    Rankings without an explicit `pos_rank` fall back to their rank order
    within position.
    """
    derived_pos_rank: dict[str, int] = {}
    counters: dict[Position, int] = {}
    for ranking in sorted(rankings, key=lambda r: r.rank):
        counters[ranking.position] = counters.get(ranking.position, 0) + 1
        derived_pos_rank[ranking.player_id] = counters[ranking.position]

    projected: dict[str, float] = {}
    for ranking in rankings:
        if ranking.projected_points is not None:
            projected[ranking.player_id] = ranking.projected_points
            continue
        pos_rank = ranking.pos_rank or derived_pos_rank[ranking.player_id]
        projected[ranking.player_id] = _curve_value(curves.get(ranking.position, []), pos_rank)
    return projected
