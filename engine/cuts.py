"""Which contracts to keep before the drop deadline, and what that does to prices.

Two things happen at once in this league's offseason. Each owner decides which
contracts to keep, which is only answerable against what those players are
worth at auction. And auction prices are set by how much money and how many
players the twelve owners collectively release -- that is, by everyone's keep
decisions. Neither is knowable without the other.

`solve_equilibrium` closes the loop by iterating to a fixed point: price the
market, let every owner re-optimize, re-price from the resulting money and
slots, repeat until the market stops moving.

The answer is genuinely sensitive to what rivals do, so the policy is a
parameter rather than an assumption. `MINIMUM_COMPLIANCE` and
`SURPLUS_MAXIMIZING` bracket the plausible range, and the gap between them is
the real uncertainty in any cut recommendation -- reporting a single number
would be false precision.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum

from data.models import Contract, ContractRules
from engine.auction import AuctionMarket, clear_market
from engine.replacement import PlayerValue


class RetentionPolicy(str, Enum):
    SURPLUS_MAXIMIZING = "surplus_maximizing"
    """Cut every contract priced below its salary. The rational play, and the
    upper bound on how much the league releases."""

    MINIMUM_COMPLIANCE = "minimum_compliance"
    """Shed only what the cap demands, losing the least value. Models
    loss-averse owners anchored on what they paid, and the lower bound."""


@dataclass(frozen=True)
class TeamRoster:
    name: str
    contracts: tuple[Contract, ...]

    @property
    def salary(self) -> int:
        return sum(c.salary for c in self.contracts)


@dataclass(frozen=True)
class RetentionPlan:
    team: str
    keep: tuple[Contract, ...]
    cut: tuple[Contract, ...]
    surplus: float
    """Total market value retained above salary owed."""

    @property
    def salary(self) -> int:
        return sum(c.salary for c in self.keep)

    def bid_budget(self, rules: ContractRules) -> int:
        return rules.salary_cap - self.salary

    def slots_to_fill(self, rules: ContractRules) -> int:
        return max(0, rules.max_roster - len(self.keep))


@dataclass(frozen=True)
class LeagueEquilibrium:
    market: AuctionMarket
    plans: dict[str, RetentionPlan]
    iterations: int
    converged: bool

    def plan(self, team: str) -> RetentionPlan:
        return self.plans[team]


def optimal_retention(
    contracts: Sequence[Contract],
    price_of: Callable[[Contract], float],
    rules: ContractRules,
) -> RetentionPlan:
    """Keep the subset maximizing retained surplus, under the cap and roster limit.

    Only contracts priced above their salary are candidates: a contract worth
    less than it costs consumes budget *and* lowers the objective, and the
    money freed by cutting it buys a replacement at market -- which yields no
    surplus by definition. So cutting is never worse.

    That leaves a two-constraint 0/1 knapsack (dollars and roster spots),
    solved exactly by dynamic programming. The state space is trivial here --
    a $300 cap by 14 spots -- so there is no reason to approximate.
    """
    team = contracts[0].team if contracts else ""
    candidates = [c for c in contracts if price_of(c) > c.salary]
    rejected = [c for c in contracts if price_of(c) <= c.salary]

    # A franchise tag can drive a salary to zero or below (the league has
    # recorded both), which would break a knapsack over non-negative weights.
    # Such a contract costs nothing and frees cap, so it is always kept and
    # its salary folds into the budget.
    free = [c for c in candidates if c.salary <= 0]
    priced = [c for c in candidates if c.salary > 0]
    budget = rules.salary_cap - sum(c.salary for c in free)
    max_keep = rules.max_roster - len(free)

    if budget < 0 or max_keep < 0:  # pathological config; keep nothing rather than crash
        return RetentionPlan(team=team, keep=(), cut=tuple(contracts), surplus=0.0)

    # best[spent][count] -> (surplus, chosen indices)
    best: dict[tuple[int, int], tuple[float, tuple[int, ...]]] = {(0, 0): (0.0, ())}
    for idx, contract in enumerate(priced):
        gain = price_of(contract) - contract.salary
        updated = dict(best)
        for (spent, count), (surplus, chosen) in best.items():
            new_spent, new_count = spent + contract.salary, count + 1
            if new_spent > budget or new_count > max_keep:
                continue
            candidate = (surplus + gain, chosen + (idx,))
            if candidate[0] > updated.get((new_spent, new_count), (float("-inf"), ()))[0]:
                updated[(new_spent, new_count)] = candidate
        best = updated

    surplus, chosen = max(best.values(), key=lambda entry: entry[0])
    kept_priced = {priced[i] for i in chosen}
    keep = tuple(c for c in contracts if c in kept_priced or c in free)
    keep_set = set(keep)
    cut = tuple(c for c in contracts if c not in keep_set)
    total = surplus + sum(price_of(c) - c.salary for c in free)
    return RetentionPlan(team=team, keep=keep, cut=cut, surplus=total, )


def minimum_compliance_retention(
    contracts: Sequence[Contract],
    price_of: Callable[[Contract], float],
    rules: ContractRules,
) -> RetentionPlan:
    """Keep everything the cap and roster limit allow, dropping worst surplus first."""
    team = contracts[0].team if contracts else ""
    keep = sorted(contracts, key=lambda c: price_of(c) - c.salary, reverse=True)
    while keep and (
        sum(c.salary for c in keep) > rules.salary_cap or len(keep) > rules.max_roster
    ):
        keep.pop()

    keep_set = set(keep)
    ordered = tuple(c for c in contracts if c in keep_set)
    return RetentionPlan(
        team=team,
        keep=ordered,
        cut=tuple(c for c in contracts if c not in keep_set),
        surplus=sum(price_of(c) - c.salary for c in ordered),
    )


_POLICIES: dict[RetentionPolicy, Callable[..., RetentionPlan]] = {
    RetentionPolicy.SURPLUS_MAXIMIZING: optimal_retention,
    RetentionPolicy.MINIMUM_COMPLIANCE: minimum_compliance_retention,
}


def solve_equilibrium(
    rosters: Sequence[TeamRoster],
    values: dict[str, PlayerValue],
    rules: ContractRules,
    num_teams: int,
    *,
    key: Callable[[Contract], str],
    policy: RetentionPolicy = RetentionPolicy.SURPLUS_MAXIMIZING,
    overrides: dict[str, tuple[Contract, ...]] | None = None,
    damping: float = 0.5,
    max_iterations: int = 200,
    tolerance: float = 0.5,
) -> LeagueEquilibrium:
    """Iterate keep decisions and prices to a fixed point.

    `values` is the whole player universe -- rostered and free agents alike --
    keyed by player id, holding value over replacement.

    `overrides` pins a team's keep set instead of optimizing it, which is how
    you ask "what happens to the market if *I* release everything?" without
    letting the solver quietly re-optimize your own roster back.

    Damping is what makes this converge. Undamped, the loop oscillates: a
    player priced above his salary is kept, which removes his money and slot
    from the market, which changes prices enough to cut him again.

    One deliberate simplification: prices are normalized over the top `slots`
    of the *whole* universe rather than of the players who end up available.
    That keeps retained and available players on one comparable scale, at the
    cost of slightly understating prices when the very best players are all
    retained (the money left over would chase a weaker pool than assumed).
    """
    overrides = overrides or {}
    retain = _POLICIES[policy]
    pool = list(values.values())

    dollars = float(num_teams * rules.salary_cap)
    slots = float(num_teams * rules.max_roster)
    market = clear_market(pool, int(dollars), int(slots), rules.min_bid)
    plans: dict[str, RetentionPlan] = {}
    converged = False
    iterations = 0

    for iterations in range(1, max_iterations + 1):
        def price_of(contract: Contract, _market: AuctionMarket = market) -> float:
            return _market.price(key(contract))

        plans = {}
        for roster in rosters:
            if roster.name in overrides:
                keep = overrides[roster.name]
                keep_set = set(keep)
                plans[roster.name] = RetentionPlan(
                    team=roster.name,
                    keep=keep,
                    cut=tuple(c for c in roster.contracts if c not in keep_set),
                    surplus=sum(price_of(c) - c.salary for c in keep),
                )
            else:
                plans[roster.name] = retain(roster.contracts, price_of, rules)

        retained_salary = sum(plan.salary for plan in plans.values())
        retained_count = sum(len(plan.keep) for plan in plans.values())
        target_dollars = float(num_teams * rules.salary_cap - retained_salary)
        target_slots = float(num_teams * rules.max_roster - retained_count)

        moved = abs(target_dollars - dollars) + abs(target_slots - slots)
        dollars = damping * dollars + (1 - damping) * target_dollars
        slots = damping * slots + (1 - damping) * target_slots
        market = clear_market(pool, int(round(dollars)), int(round(slots)), rules.min_bid)

        if moved < tolerance:
            converged = True
            break

    return LeagueEquilibrium(
        market=market, plans=plans, iterations=iterations, converged=converged
    )
