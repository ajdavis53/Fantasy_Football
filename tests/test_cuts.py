from __future__ import annotations

import pytest

from data.models import Contract, ContractRules, Position
from engine.auction import clear_market
from engine.cuts import (
    RetentionPolicy,
    TeamRoster,
    minimum_compliance_retention,
    optimal_retention,
    solve_equilibrium,
)
from engine.replacement import PlayerValue

RULES = ContractRules(salary_cap=100, max_roster=3, min_roster=1)


def contract(name: str, salary: int, team: str = "T") -> Contract:
    return Contract(player_name=name, salary=salary, position=Position.RB, team=team)


def prices(mapping: dict[str, float]):
    return lambda c: mapping[c.player_name]


def test_keeps_only_contracts_worth_more_than_their_salary():
    roster = [contract("bargain", 10), contract("fair", 20), contract("overpaid", 60)]
    plan = optimal_retention(roster, prices({"bargain": 40, "fair": 20, "overpaid": 30}), RULES)

    assert [c.player_name for c in plan.keep] == ["bargain"]
    assert {c.player_name for c in plan.cut} == {"fair", "overpaid"}
    assert plan.surplus == pytest.approx(30)


def test_cutting_a_break_even_contract_is_preferred():
    """Freeing the money buys a replacement at market, which yields the same zero surplus."""
    plan = optimal_retention([contract("even", 25)], prices({"even": 25}), RULES)
    assert plan.keep == ()


def test_respects_the_salary_cap_when_everything_is_a_bargain():
    roster = [contract("a", 60), contract("b", 55), contract("c", 30)]
    plan = optimal_retention(roster, prices({"a": 75, "b": 70, "c": 40}), RULES)

    assert plan.salary <= RULES.salary_cap
    # b + c (surplus 25) beats a + c (surplus 25) only on ties; a + b breaks the cap
    assert plan.surplus == pytest.approx(25)


def test_knapsack_beats_greedy_on_surplus():
    """Greedy by surplus takes 'big' and stalls; the optimum takes the two smaller ones."""
    roster = [contract("big", 100), contract("x", 50), contract("y", 50)]
    plan = optimal_retention(roster, prices({"big": 130, "x": 75, "y": 75}), RULES)

    assert {c.player_name for c in plan.keep} == {"x", "y"}
    assert plan.surplus == pytest.approx(50)


def test_respects_the_roster_limit():
    rules = ContractRules(salary_cap=100, max_roster=2, min_roster=1)
    roster = [contract(n, 5) for n in "abcd"]
    plan = optimal_retention(roster, prices({n: 20 for n in "abcd"}), rules)
    assert len(plan.keep) == 2


def test_zero_and_negative_salaries_are_always_kept():
    """A franchise tag can drive salary to $0 or below; such a contract frees cap."""
    roster = [contract("tagged", -2), contract("normal", 40)]
    plan = optimal_retention(roster, prices({"tagged": 20, "normal": 50}), RULES)

    assert {c.player_name for c in plan.keep} == {"tagged", "normal"}
    assert plan.salary == 38


def test_minimum_compliance_keeps_everything_the_cap_allows():
    roster = [contract("a", 50), contract("b", 40), contract("c", 30)]
    plan = minimum_compliance_retention(roster, prices({"a": 10, "b": 10, "c": 10}), RULES)

    assert plan.salary <= RULES.salary_cap
    assert len(plan.keep) == 2  # sheds only the worst contract, despite all three being bad
    assert "c" not in {c.player_name for c in plan.cut}  # cheapest surplus-per-dollar survives


def test_the_two_policies_bracket_each_other():
    """Minimum compliance always retains at least as much salary as surplus-maximizing."""
    roster = [contract("a", 50), contract("b", 40), contract("c", 30)]
    p = prices({"a": 10, "b": 10, "c": 10})
    assert minimum_compliance_retention(roster, p, RULES).salary >= optimal_retention(roster, p, RULES).salary


def test_plan_reports_budget_and_slots():
    plan = optimal_retention([contract("a", 30)], prices({"a": 90}), RULES)
    assert plan.bid_budget(RULES) == 70
    assert plan.slots_to_fill(RULES) == 2


# --- equilibrium -----------------------------------------------------------

def league(num_teams: int, salary: int, per_team: int = 2) -> list[TeamRoster]:
    return [
        TeamRoster(
            name=f"team{t}",
            contracts=tuple(
                contract(f"p{t}_{i}", salary, team=f"team{t}") for i in range(per_team)
            ),
        )
        for t in range(num_teams)
    ]


def universe(rosters: list[TeamRoster], free_agents: int = 10) -> dict[str, PlayerValue]:
    pool = {}
    for roster in rosters:
        for i, c in enumerate(roster.contracts):
            pool[c.player_name] = PlayerValue(c.player_name, Position.RB, 30.0 - i)
    for i in range(free_agents):
        pool[f"fa{i}"] = PlayerValue(f"fa{i}", Position.RB, 5.0)
    return pool


def test_equilibrium_converges():
    rosters = league(4, salary=20)
    result = solve_equilibrium(
        rosters, universe(rosters), RULES, num_teams=4,
        key=lambda c: c.player_name,
    )
    assert result.converged, f"did not settle in {result.iterations} iterations"


def test_equilibrium_conserves_the_leagues_money():
    """Retained salary plus auction dollars must equal the league's total cap."""
    rosters = league(4, salary=20)
    result = solve_equilibrium(
        rosters, universe(rosters), RULES, num_teams=4, key=lambda c: c.player_name
    )
    retained = sum(plan.salary for plan in result.plans.values())
    assert retained + result.market.dollars == pytest.approx(4 * RULES.salary_cap, abs=2)


def test_minimum_compliance_leaves_a_poorer_auction_than_teardown():
    """The core scenario spread: how much the league releases sets the price level."""
    rosters = league(4, salary=45)
    kwargs = dict(num_teams=4, key=lambda c: c.player_name)
    lean = solve_equilibrium(
        rosters, universe(rosters), RULES, policy=RetentionPolicy.MINIMUM_COMPLIANCE, **kwargs
    )
    rich = solve_equilibrium(
        rosters, universe(rosters), RULES, policy=RetentionPolicy.SURPLUS_MAXIMIZING, **kwargs
    )
    assert lean.market.dollars < rich.market.dollars


def test_overrides_pin_a_teams_keep_set():
    """Asking 'what if I release everything?' must not be re-optimized away."""
    rosters = league(4, salary=20)
    result = solve_equilibrium(
        rosters, universe(rosters), RULES, num_teams=4,
        key=lambda c: c.player_name,
        overrides={"team0": ()},
    )
    assert result.plan("team0").keep == ()
    assert result.plan("team0").bid_budget(RULES) == RULES.salary_cap
    assert len(result.plan("team0").cut) == 2
