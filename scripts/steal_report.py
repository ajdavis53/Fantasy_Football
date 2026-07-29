"""Steal-round analysis: what to offer, on whom, and whether to bother.

The steal round is a single day of group texts, and the pick is one-shot. This
prices every stealable contract in the league, both as an acquisition and as a
weapon, and prices your own roster's exposure the other way.

    uv run python scripts/steal_report.py rosters.xlsx etr.csv --pick 8

The comparison that matters is *not* market value against salary. The auction
clears at market by construction, so a dollar spent bidding buys a dollar of
value; a steal is only worth making if it beats that. Hence the `$/$` column.

Everything above 1.00 there comes from the distress assumption -- that an owner
already over the cap values a contract below market, because keeping it forces
a cut elsewhere. Run with `--distress 0` to see the other extreme: against
owners who value their players at full market, the keep formula guarantees
every pry price exceeds market value, and no steal is worth making for value
at all. The truth is in between, and which end it sits nearer is a judgement
about twelve specific people rather than anything this can compute.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from data.contracts import min_offer_to_pry, steal_keep_price
from data.models import Contract
from engine.dynasty import flat_market, value_contract
from engine.steal import rank_steal_targets
from app.session import Session

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LEAGUE = ROOT / "config" / "leagues" / "ffl_ny.yaml"

# How far below market a cap-squeezed owner values a contract he must shed
# anyway. An assumption, not a measurement -- capped so that even the most
# distressed owner is only modelled as a 30% discount.
DEFAULT_DISTRESS = 0.30


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roster", type=Path)
    parser.add_argument("etr", type=Path)
    parser.add_argument("--league", type=Path, default=DEFAULT_LEAGUE)
    parser.add_argument("--team", default="Andrew's Team")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--pick", type=int, default=8, help="your slot in the steal order")
    parser.add_argument("--horizon", type=int, default=3)
    parser.add_argument("--discount", type=float, default=0.8,
                        help="dynasty weighting; higher favours future seasons")
    parser.add_argument("--distress", type=float, default=DEFAULT_DISTRESS,
                        help="max discount a cap-squeezed owner puts on his own player; "
                             "0 models owners who value at full market")
    args = parser.parse_args()

    session = Session.load(args.league, args.roster, args.etr,
                           my_team=args.team, season=args.season)
    rules = session.rules
    session.apply_recommendation()          # price the world you will actually be in
    equilibrium = session.equilibrium()
    market = equilibrium.market
    auction = session.start_auction()

    over_cap = {r.name: max(0, r.salary - rules.salary_cap) for r in session.rosters}

    def value_of(contract: Contract) -> float:
        return market.price(session.key(contract))

    def distress(contract: Contract) -> float:
        return 1.0 - min(args.distress, over_cap.get(contract.team, 0) / 300)

    targets = rank_steal_targets(
        [c for r in session.rosters for c in r.contracts],
        value_of, rules, args.season,
        defender_discount=distress,
        exclude_teams=[session.my_team],
    )

    # Best player at each position who will actually reach the auction.
    best_available: dict[object, tuple[str, float]] = {}
    for advice in auction.board(limit=500):
        pos = advice.player.position
        if pos not in best_available or advice.par > best_available[pos][1]:
            best_available[pos] = (advice.player.name, advice.par)

    print(f"=== steal round {args.season} — {session.my_team}, pick {args.pick} of "
          f"{session.league.num_teams} ===")
    print(f"{args.pick - 1} owners choose before you, so plan {args.pick - 1} deep.\n")

    header = (f"{'PLAYER':21}{'POS':4}{'OWNER':22}{'SAL':>4}{'VAL':>5}{'PRY':>5}"
              f"{'DMG':>5}{'3YR':>6}{'$/$':>7}   best available at position")
    print(header)
    print("-" * len(header))
    for evaluation in targets[:16]:
        contract = evaluation.contract
        pos = contract.position
        alt_name, alt_par = best_available.get(pos, ("nothing", 0.0))
        # Value per dollar, against the auction's baseline of 1.0. The auction
        # clears at market by construction, so a dollar spent there buys a
        # dollar of value; a steal is worth making only if it beats that.
        # (Subtracting the alternative's price from both sides, as an earlier
        # draft of this did, cancels it out and just restates surplus.)
        per_dollar = evaluation.market_value / max(evaluation.offer, 1)
        multi = value_contract(
            Contract(player_name="", salary=evaluation.offer),
            flat_market(evaluation.market_value, args.horizon),
            rules, args.season, discount_rate=args.discount,
        ).total_value
        print(f"{contract.player_name[:20]:21}{pos.value if pos else '':4}"
              f"{(contract.team or '')[:21]:22}{contract.salary:>4}"
              f"{evaluation.market_value:>5.0f}{evaluation.offer:>5}"
              f"{evaluation.cap_damage_if_kept:>5}{multi:>6.0f}"
              f"  {per_dollar:>5.2f}   {alt_name[:16]:17} ${alt_par:.0f}")

    print("\n  VAL = equilibrium market value    PRY = offer that makes keeping cost more than he is worth")
    print("  DMG = salary his owner absorbs if he keeps him")
    print(f"  3YR = discounted surplus over {args.horizon} seasons at {args.discount:g} weighting,")
    print("        holding market value flat -- there are no ages in the data, so this")
    print("        understates decline for veterans and growth for the young")
    print("  $/$ = value per dollar at the pry price. The auction clears at market, so a")
    print("        dollar spent there buys a dollar of value: below 1.00, just bid instead")

    print("\n=== your exposure ===")
    kept = session.kept_contracts()
    if not kept:
        print("  nothing to defend -- you are releasing every contract")
    for contract in kept:
        value = value_of(contract)
        offer = min_offer_to_pry(contract.salary, value, rules)
        print(f"  {contract.player_name:22} ${contract.salary:>3} vs market ${value:.0f}: "
              f"someone must offer ${offer} to pry him; "
              f"keeping then costs you ${steal_keep_price(offer, contract.salary, rules)}")

    print("\n=== tag timing ===")
    print("  6.1 allows the franchise tag any time up to the drop deadline, so it can be")
    print("  applied before the steal round. Doing so *raises* the price to pry the player,")
    print("  because the keep price climbs from a lower base at 85c per dollar of premium:")
    for contract in session.my_roster.contracts:
        if session.key(contract) not in session.tagged:
            continue
        # `contract` here is the raw roster entry, so its salary is the
        # untagged figure; the tag takes the discount off it.
        untagged = contract.salary
        tagged = untagged - rules.franchise_discount
        value = market.price(session.key(contract))
        print(f"    {contract.player_name}: untagged ${untagged} -> pry "
              f"${min_offer_to_pry(untagged, value, rules)};  "
              f"tagged ${tagged} -> pry ${min_offer_to_pry(tagged, value, rules)}"
              f"   (market ${value:.1f})")


if __name__ == "__main__":
    main()
