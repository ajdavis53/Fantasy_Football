"""Run a full mock draft to exercise the whole stack before draft day.

Usage:
    uv run python scripts/mock_draft.py <league_yaml> <etr_export> [--slot N] [--seed N]

I pick via engine.recommend; opponents pick by ADP with a little noise, which
is a fair approximation of a real room since ADP is by definition what the
market does. The point is to shake out integration bugs -- an illegal final
roster, a position that never gets drafted, an exhausted board -- that unit
tests on a synthetic board will not surface.
"""
from __future__ import annotations

import argparse
import collections
import random

from config.settings import load_league_settings
from data.models import Position
from engine.draft_state import DraftState
from engine.recommend import recommend
from scripts.build_board import build_board

# How far an opponent will stray from strict ADP order, in ADP positions.
ADP_NOISE = 6.0


def opponent_pick(board_rows: list[dict], state: DraftState, rng: random.Random) -> str:
    """Best available by ADP, jittered so the room is not perfectly predictable."""
    available = [r for r in board_rows if not state.is_drafted(r["player_id"])]
    if not available:
        return ""

    def key(row: dict) -> float:
        adp = row["adp"] if row.get("adp") is not None else row["etr_rank"]
        return adp + rng.gauss(0, ADP_NOISE)

    return min(available, key=key)["player_id"]


def run_mock(league_path: str, etr_path: str, slot: int | None, seed: int) -> dict:
    rng = random.Random(seed)
    league = load_league_settings(league_path)
    if slot is not None:
        league.draft_slot = slot

    board = build_board(league_path, etr_path)
    board_by_id = {r["player_id"]: r for r in board}
    state = DraftState(league=league)

    while not state.is_complete:
        if state.on_the_clock_team_index == state.my_team_index:
            recs = recommend(state, board, league, top_n=1)
            if not recs:
                break
            state.record_pick(recs[0].player_id)
        else:
            player_id = opponent_pick(board, state, rng)
            if not player_id:
                break
            state.record_pick(player_id)

    return {"league": league, "state": state, "board_by_id": board_by_id}


def starter_requirements(league) -> dict[str, int]:
    required: collections.Counter = collections.Counter()
    for slot in league.roster_slots.dedicated_slots():
        for position in slot.eligible_positions:
            required[position.value] += slot.count
    return dict(required)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("league_yaml")
    parser.add_argument("etr_export")
    parser.add_argument("--slot", type=int, default=None)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    result = run_mock(args.league_yaml, args.etr_export, args.slot, args.seed)
    league, state, board_by_id = result["league"], result["state"], result["board_by_id"]

    my_ids = state.roster_player_ids(state.my_team_index)
    counts = collections.Counter(board_by_id[p]["position"] for p in my_ids)

    print(f"{league.name} — slot {league.draft_slot}/{league.num_teams}, {league.rounds} rounds")
    print(f"picks made: {len(state.pick_history)} / {state.total_picks}")
    print(f"\nyour roster ({len(my_ids)}): {dict(counts)}")
    for player_id in my_ids:
        row = board_by_id[player_id]
        adp = f"{row['adp']:.0f}" if row.get("adp") is not None else "—"
        print(f"  {row['position']:<4} {row['name']:<24} ETR {row['etr_rank']:>3}  ADP {adp:>4}")

    required = starter_requirements(league)
    shortfalls = {
        pos: (counts.get(pos, 0), need)
        for pos, need in required.items()
        if counts.get(pos, 0) < need
    }
    print()
    if shortfalls:
        print(f"INCOMPLETE STARTING LINEUP: {shortfalls}")
        raise SystemExit(1)
    print(f"starting lineup requirements met: {required}")


if __name__ == "__main__":
    main()
