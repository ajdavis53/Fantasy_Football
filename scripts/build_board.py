"""Build a full VBD-ranked, tiered draft board for one league from an ETR CSV export.

Usage: uv run python scripts/build_board.py <league_yaml> <etr_csv>
"""
from __future__ import annotations

import sys

from config.settings import load_league_settings
from data.ingest_etr import load_etr_rankings
from engine.replacement import PlayerValue
from engine.tiers import compute_gap_tiers, tiers_from_rankings
from engine.vbd import compute_vbd


def build_board(league_path: str, etr_csv_path: str) -> list[dict]:
    league = load_league_settings(league_path)
    players, rankings = load_etr_rankings(etr_csv_path)
    players_by_id = {p.player_id: p for p in players}

    player_values = [
        PlayerValue(player_id=r.player_id, position=r.position, value=r.projected_points or 0.0)
        for r in rankings
    ]

    vbd = compute_vbd(player_values, league, baseline="VORP")
    tiers = tiers_from_rankings(rankings) or compute_gap_tiers(player_values)

    board = []
    for r in rankings:
        player = players_by_id[r.player_id]
        board.append(
            {
                "player_id": r.player_id,
                "name": player.name,
                "team": player.nfl_team,
                "position": r.position.value,
                "etr_rank": r.rank,
                "tier": tiers.get(r.player_id),
                "vorp": round(vbd.get(r.player_id, 0.0), 1),
            }
        )
    board.sort(key=lambda row: row["vorp"], reverse=True)
    return board


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: build_board.py <league_yaml> <etr_csv>", file=sys.stderr)
        raise SystemExit(1)

    board = build_board(sys.argv[1], sys.argv[2])
    header = f"{'RANK':>4} {'NAME':<24} {'POS':<4} {'TEAM':<5} {'TIER':>4} {'VORP':>7}"
    print(header)
    print("-" * len(header))
    for i, row in enumerate(board, start=1):
        print(
            f"{i:>4} {row['name']:<24} {row['position']:<4} {row['team'] or '':<5} "
            f"{row['tier'] or '':>4} {row['vorp']:>7}"
        )


if __name__ == "__main__":
    main()
