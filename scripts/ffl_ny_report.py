"""End-to-end offseason report for FFL-NY, from the real roster and ETR files.

Runs the whole Phase 1 pipeline in one pass -- ingest, invert published auction
values, re-clear the market, solve every owner's cut decision to a fixed point,
then rank steal targets -- and prints the numbers the 8/17 and 8/3 decisions
turn on.

    uv run python scripts/ffl_ny_report.py <roster.xlsx> <etr_auction_values.csv>

Deliberately a script and not a test: the numbers move whenever ETR republishes
or an owner drops somebody, so pinning them would only produce a test that
fails for the wrong reason. What is asserted in the suite is the *behaviour* of
each stage; what this does is show the current answer.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from config.settings import load_league_settings
from data.ingest_etr import load_etr_auction_values
from data.ingest_roster import (
    contract_player_id,
    link_contracts_to_players,
    load_roster_workbook,
)
from data.models import Contract
from engine.auction import implied_vorp, max_affordable_bid
from engine.cuts import RetentionPolicy, TeamRoster, solve_equilibrium
from engine.replacement import PlayerValue, positions_with_demand
from engine.steal import rank_steal_targets

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LEAGUE = ROOT / "config" / "leagues" / "ffl_ny.yaml"

# 2025 rookie protections held all year (rule 7.3): exempt from escalation and
# from steal attempts through 2026. Sourced from the league's rules sheet; see
# docs/ffl-ny/league-rules.md.
ROOKIE_PROTECTED_THROUGH_2026 = {
    "Travis Hunter", "Emeka Egbuka", "Tyler Warren", "Bhayshul Tuten",
}


def build_universe(players, values, league) -> dict[str, PlayerValue]:
    """Published auction values -> value over replacement, for startable positions only."""
    startable = positions_with_demand(league)
    vorp = implied_vorp(values, league.contract_rules.min_bid)
    by_id = {p.player_id: p for p in players}
    return {
        pid: PlayerValue(player_id=pid, position=by_id[pid].position, value=v)
        for pid, v in vorp.items()
        if by_id[pid].position in startable
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roster", type=Path, help="preseason roster & salary workbook")
    parser.add_argument("etr", type=Path, help="ETR auction values export (.csv or .xlsx)")
    parser.add_argument("--league", type=Path, default=DEFAULT_LEAGUE)
    parser.add_argument("--team", default="Andrew's Team")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--value-column", default="half_ppr")
    args = parser.parse_args()

    league = load_league_settings(args.league)
    rules = league.contract_rules
    if rules is None:
        raise SystemExit(f"{args.league} has no `contracts:` block; not an auction league")

    players, published = load_etr_auction_values(args.etr, args.value_column)
    universe = build_universe(players, published, league)
    imports = load_roster_workbook(args.roster)

    # Fold in the rookie protections the workbook cannot know about.
    def protect(contract: Contract) -> Contract:
        if contract.player_name in ROOKIE_PROTECTED_THROUGH_2026:
            return Contract(**{**vars(contract), "rookie_protected_through": args.season})
        return contract

    rosters = [
        TeamRoster(name=t.team, contracts=tuple(protect(c) for c in t.contracts))
        for t in imports
    ]
    all_contracts = [c for r in rosters for c in r.contracts]
    linked, unmatched = link_contracts_to_players(all_contracts, players)

    def key(contract: Contract) -> str:
        raw = contract_player_id(contract)
        return linked.get(raw, raw)

    print(f"=== {league.name} {args.season} ===")
    print(f"published values sum to ${sum(published.values()):,.0f} "
          f"({league.num_teams} teams x ${sum(published.values()) / league.num_teams:,.0f})")
    committed = sum(t.salary for t in imports)
    total_cap = league.num_teams * rules.salary_cap
    print(f"committed ${committed:,} against ${total_cap:,} of cap "
          f"-- the league is ${committed - total_cap:,} over")
    print(f"{sum(1 for t in imports if t.salary > rules.salary_cap)} of {len(imports)} teams over the cap")
    if unmatched:
        print(f"unranked (treated as replacement level): "
              f"{', '.join(c.player_name for c in unmatched)}")

    scenarios = {}
    for policy in (RetentionPolicy.MINIMUM_COMPLIANCE, RetentionPolicy.SURPLUS_MAXIMIZING):
        scenarios[policy] = solve_equilibrium(
            rosters, universe, rules, league.num_teams, key=key, policy=policy
        )

    print(f"\n{'scenario':26}{'auction $':>11}{'slots':>7}{'$/slot':>8}"
          f"{'your $':>8}{'your share':>12}")
    for policy, result in scenarios.items():
        plan = result.plan(args.team)
        teardown = solve_equilibrium(
            rosters, universe, rules, league.num_teams, key=key,
            policy=policy, overrides={args.team: ()},
        )
        mine = rules.salary_cap
        share = mine / teardown.market.dollars if teardown.market.dollars else 0
        print(f"{policy.value:26}{result.market.dollars:>11,}{result.market.slots:>7}"
              f"{result.market.dollars / max(result.market.slots, 1):>8.1f}"
              f"{plan.bid_budget(rules):>8}{share:>11.0%}")
    print("  (`your share` is what you would control after releasing every contract)")

    equilibrium = scenarios[RetentionPolicy.SURPLUS_MAXIMIZING]
    market = equilibrium.market
    mine = next(r for r in rosters if r.name == args.team)

    print(f"\n=== {args.team} at equilibrium prices ===")
    print(f"{'PLAYER':24}{'POS':5}{'SAL':>5}{'MKT':>6}{'SURPLUS':>9}")
    for contract in sorted(mine.contracts, key=lambda c: market.surplus(key(c), c.salary), reverse=True):
        surplus = market.surplus(key(contract), contract.salary)
        print(f"{contract.player_name[:23]:24}{contract.position.value:5}"
              f"{contract.salary:>5}{market.price(key(contract)):>6.0f}{surplus:>9.1f}"
              f"{'  KEEP' if surplus > 0 else ''}")

    plan = equilibrium.plan(args.team)
    print(f"keep {len(plan.keep)} at ${plan.salary} -> ${plan.bid_budget(rules)} to bid, "
          f"{plan.slots_to_fill(rules)} slots to fill "
          f"(max single bid ${max_affordable_bid(plan.bid_budget(rules), plan.slots_to_fill(rules))})")

    print(f"\n=== steal targets (season {args.season}) ===")
    print(f"{'PLAYER':22}{'OWNER':24}{'SAL':>4}{'MKT':>5}{'PRY':>5}{'DMG':>5}")
    over_cap = {t.team: max(0, t.salary - rules.salary_cap) for t in imports}
    targets = rank_steal_targets(
        all_contracts,
        lambda c: market.price(key(c)),
        rules,
        args.season,
        # An owner over the cap must shed salary anyway, so a contract is worth
        # less to him than to the market -- he lets go at a lower offer.
        defender_discount=lambda c: 1.0 - min(0.3, over_cap.get(c.team, 0) / 300),
        exclude_teams=[args.team],
    )
    for evaluation in targets[:12]:
        contract = evaluation.contract
        print(f"{contract.player_name[:21]:22}{(contract.team or '')[:23]:24}"
              f"{contract.salary:>4}{evaluation.market_value:>5.0f}"
              f"{evaluation.offer:>5}{evaluation.cap_damage_if_kept:>5}")
    print("  PRY = offer that makes keeping cost more than he is worth to his owner")
    print("  DMG = salary the owner absorbs if he keeps him at that offer")

    protected = [c for c in all_contracts if not c.is_steal_eligible(args.season)]
    print(f"\nsteal-proof (2025 rookie protection): "
          f"{', '.join(f'{c.player_name} (${c.salary})' for c in protected)}")


if __name__ == "__main__":
    main()
