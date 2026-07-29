"""Rehearse a full auction before draft night.

The live assistant gets exactly one chance to work: three hours, in person, on
24 August, with no opportunity to debug. This drives a whole synthetic auction
through the real engine -- every team bidding to its own affordability limit
until all rosters are full -- so the code paths that only appear late in a
draft (opponents running out of money, the last slot, an empty board) are
exercised in advance rather than discovered at the table.

    uv run python scripts/mock_auction.py rosters.xlsx etr_auction_values.csv

Prints a running trace and a set of invariant checks. It is not a test of who
*should* win a lot -- bidders here are crude -- it is a test that the state
machine stays coherent for a few hundred sales.
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

from app.session import Session

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LEAGUE = ROOT / "config" / "leagues" / "ffl_ny.yaml"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roster", type=Path)
    parser.add_argument("etr", type=Path)
    parser.add_argument("--league", type=Path, default=DEFAULT_LEAGUE)
    parser.add_argument("--team", default="Andrew's Team")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--trace", type=int, default=12, help="sales to print")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    session = Session.load(args.league, args.roster, args.etr, my_team=args.team)
    session.apply_recommendation()
    auction = session.start_auction()

    print(f"opening: ${auction.remaining_dollars():,} across {auction.remaining_slots()} slots, "
          f"{len(auction.available())} players available, inflation {auction.inflation():.3f}")

    sold = 0
    while auction.remaining_slots() > 0:
        board = auction.board(limit=1)
        if not board:
            print("board exhausted before every roster filled")
            break
        advice = board[0]

        # Crude bidders: whoever can afford the most pays near the going rate,
        # with noise, floored at the minimum bid.
        bidders = [s for s in auction.all_status() if s.can_bid]
        if not bidders:
            print("nobody can bid; stopping")
            break
        winner = max(bidders, key=lambda s: s.max_bid)
        price = max(
            auction.rules.min_bid,
            min(winner.max_bid, round(advice.adjusted * rng.uniform(0.75, 1.3))),
        )
        sale = auction.record(advice.player.player_id, winner.team, price)
        sold += 1
        if sold <= args.trace:
            print(f"  {sale.player_name:24} -> {sale.team[:20]:22} ${sale.price:>3}"
                  f"   inflation now {auction.inflation():.2f}")

        assert auction.status(winner.team).budget >= 0, f"{winner.team} went negative"

    print(f"\n{sold} lots sold")
    print(f"{'TEAM':24}{'ROSTER':>8}{'SPENT':>7}{'LEFT':>6}")
    for status in sorted(auction.all_status(), key=lambda s: s.team):
        print(f"{status.team[:23]:24}{status.filled:>4}/{auction.rules.max_roster:<3}"
              f"{status.spent:>7}{status.budget:>6}")

    failures = []
    for status in auction.all_status():
        if status.budget < 0:
            failures.append(f"{status.team} finished ${-status.budget} over the cap")
        if status.filled > auction.rules.max_roster:
            failures.append(f"{status.team} finished with {status.filled} players")
    if len(auction.sold_ids) != len(auction.sales):
        failures.append("a player was sold twice")

    for _ in range(sold):
        auction.undo()
    if auction.sales:
        failures.append("undo did not unwind the full auction")

    print("\n" + ("FAILED:\n  " + "\n  ".join(failures) if failures else "all invariants held"))


if __name__ == "__main__":
    main()
