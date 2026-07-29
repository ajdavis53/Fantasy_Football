"""The whole 8/17 decision: which contracts to keep, and who to franchise tag.

Keeping and tagging cannot be decided separately. A tag cuts $10 off a salary
(6.2), which changes both whether that contract is worth keeping and how much
cap is left for the others -- so the tag has to be chosen *inside* the
retention optimization, not bolted on before or after it.

The search is exhaustive over single tags: try each eligible player, re-solve
retention with his discounted salary, and keep whichever beats the untagged
baseline. Tagging a player only to cut him is pointless, so candidates whose
solution drops the tagged contract are discarded rather than scored.

A second tag (held by owners who lost a player to a steal, 15.6) is allocated
greedily on top of the first rather than searched jointly. That is a deliberate
approximation -- the exact version is quadratic in roster size for a
vanishingly rare case, and the two tags rarely interact, since they compete
only through the cap.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from data.contracts import can_franchise_tag, franchise_tag_salary
from data.models import Contract, ContractRules
from engine.cuts import RetentionPlan, optimal_retention


@dataclass(frozen=True)
class TagChoice:
    contract: Contract
    original_salary: int
    tagged_salary: int
    gain: float
    """Surplus this tag adds over the best plan without it."""


@dataclass(frozen=True)
class RosterPlan:
    retention: RetentionPlan
    tags: tuple[TagChoice, ...]
    rejected_tags: tuple[tuple[Contract, str], ...]
    """Contracts that could not be tagged, with the rule that blocked them."""

    @property
    def keep(self) -> tuple[Contract, ...]:
        return self.retention.keep

    @property
    def cut(self) -> tuple[Contract, ...]:
        return self.retention.cut

    @property
    def salary(self) -> int:
        return self.retention.salary

    @property
    def surplus(self) -> float:
        return self.retention.surplus

    def bid_budget(self, rules: ContractRules) -> int:
        return self.retention.bid_budget(rules)

    def slots_to_fill(self, rules: ContractRules) -> int:
        return self.retention.slots_to_fill(rules)


def taggable(
    contracts: Sequence[Contract], season: int, rules: ContractRules
) -> tuple[list[Contract], list[tuple[Contract, str]]]:
    """Split a roster into (eligible for the franchise tag, blocked with reason)."""
    eligible, blocked = [], []
    for contract in contracts:
        allowed, reason = can_franchise_tag(contract, season, rules)
        (eligible if allowed else blocked).append(contract if allowed else (contract, reason))
    return eligible, blocked


def _tagged(contract: Contract, season: int, rules: ContractRules) -> Contract:
    return replace(
        contract,
        salary=franchise_tag_salary(contract.salary, rules),
        franchise_tagged_season=season,
    )


def _best_single_tag(
    contracts: Sequence[Contract],
    price_of: Callable[[Contract], float],
    rules: ContractRules,
    season: int,
    baseline: RetentionPlan,
) -> tuple[RetentionPlan, TagChoice | None]:
    eligible, _ = taggable(contracts, season, rules)
    best_plan, best_tag = baseline, None

    for candidate in eligible:
        swapped = _tagged(candidate, season, rules)
        modified = [swapped if c is candidate else c for c in contracts]
        plan = optimal_retention(modified, price_of, rules)
        if swapped not in plan.keep:
            continue  # a tag spent on a player we then cut buys nothing
        if plan.surplus > best_plan.surplus:
            best_plan = plan
            best_tag = TagChoice(
                contract=candidate,
                original_salary=candidate.salary,
                tagged_salary=swapped.salary,
                gain=plan.surplus - baseline.surplus,
            )
    return best_plan, best_tag


def plan_roster(
    contracts: Sequence[Contract],
    price_of: Callable[[Contract], float],
    rules: ContractRules,
    season: int,
    *,
    tags_available: int = 1,
) -> RosterPlan:
    """Solve the keep/cut/tag decision jointly.

    `price_of` is the market price of a contract, normally an
    `AuctionMarket.price` bound to a solved equilibrium -- so the plan is only
    as good as the scenario it was priced under. Run it against both
    `RetentionPolicy` brackets rather than trusting one number.
    """
    _, blocked = taggable(contracts, season, rules)
    plan = optimal_retention(contracts, price_of, rules)
    working = list(contracts)
    tags: list[TagChoice] = []

    for _ in range(max(0, min(tags_available, rules.max_franchise_tags))):
        candidate_plan, tag = _best_single_tag(working, price_of, rules, season, plan)
        if tag is None:
            break
        plan = candidate_plan
        tags.append(tag)
        working = [
            _tagged(c, season, rules) if c is tag.contract else c for c in working
        ]

    return RosterPlan(retention=plan, tags=tuple(tags), rejected_tags=tuple(blocked))
