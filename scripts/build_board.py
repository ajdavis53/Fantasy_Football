"""Build a VBD-ranked, tiered draft board for one league from an ETR export.

Usage:
    uv run python scripts/build_board.py <league_yaml> <etr_export> [--limit N]

The export may be ETR's .xlsx cheat sheet or a .csv. Because ETR's Top-300
carries no projected points, points come from `data/projections.py`, which
fits historical points-by-positional-rank curves under this league's own
scoring rules.
"""
from __future__ import annotations

import argparse

from config.settings import load_league_settings
from data.ingest_etr import load_etr_rankings
from data.projections import fit_positional_curves, project_points
from engine.replacement import PlayerValue, filter_to_rosterable
from engine.tiers import compute_gap_tiers, tiers_from_rankings
from engine.vbd import compute_vbd


def build_board(league_path: str, etr_path: str) -> list[dict]:
    league = load_league_settings(league_path)
    players, rankings = load_etr_rankings(etr_path)
    players_by_id = {p.player_id: p for p in players}

    curves = fit_positional_curves(league.scoring)
    points = project_points(rankings, curves)

    player_values = filter_to_rosterable(
        [
            PlayerValue(player_id=r.player_id, position=r.position, value=points[r.player_id])
            for r in rankings
        ],
        league,
    )
    rosterable_ids = {pv.player_id for pv in player_values}

    vbd = compute_vbd(player_values, league, baseline="VORP")
    tiers = tiers_from_rankings(rankings) or compute_gap_tiers(player_values)

    board = []
    for r in rankings:
        if r.player_id not in rosterable_ids:
            continue
        player = players_by_id[r.player_id]
        board.append(
            {
                "player_id": r.player_id,
                "name": player.name,
                "team": player.nfl_team,
                "position": r.position.value,
                "etr_rank": r.rank,
                "pos_rank": r.pos_rank,
                "tier": tiers.get(r.player_id),
                "points": round(points[r.player_id], 1),
                "vorp": round(vbd.get(r.player_id, 0.0), 1),
                "adp": r.adp,
                "rank_diff": r.rank_diff,
            }
        )
    board.sort(key=lambda row: row["vorp"], reverse=True)
    return board


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("league_yaml")
    parser.add_argument("etr_export")
    parser.add_argument("--limit", type=int, default=40, help="rows to print (default 40)")
    args = parser.parse_args()

    board = build_board(args.league_yaml, args.etr_export)

    header = (
        f"{'#':>3} {'NAME':<24} {'POS':<4} {'TM':<4} {'TIER':>4} "
        f"{'PTS':>7} {'VORP':>7} {'ETR':>4} {'ADP':>6} {'EDGE':>6}"
    )
    print(header)
    print("-" * len(header))
    for i, row in enumerate(board[: args.limit], start=1):
        edge = f"{row['rank_diff']:+.1f}" if row["rank_diff"] is not None else ""
        adp = f"{row['adp']:.1f}" if row["adp"] is not None else ""
        print(
            f"{i:>3} {row['name']:<24} {row['position']:<4} {row['team'] or '':<4} "
            f"{row['tier'] or '':>4} {row['points']:>7} {row['vorp']:>7} "
            f"{row['etr_rank']:>4} {adp:>6} {edge:>6}"
        )
    print()
    print("EDGE = ADP - ETR rank. Positive means ETR rates them above the market (value);")
    print("negative means the market drafts them ahead of ETR's rank (fade).")


if __name__ == "__main__":
    main()
