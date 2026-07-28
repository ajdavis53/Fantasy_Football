"""The salary lifecycle of a dynasty auction league.

Every function here is one league rule, kept pure and free of I/O so the rule
can be tested against the league's own historical records. Rounding is
specified per-rule rather than globally, because the rulebook is not
consistent about it: the trade discount says "Round(...)" (spreadsheet
half-up) while the steal keep price says "Rounded Up" (ceiling).

Section numbers refer to `docs/ffl-ny/league-rules.md`.
"""
from __future__ import annotations

import math
from dataclasses import replace

from data.models import Contract, ContractRules


def _round_half_up(value: float) -> int:
    """Spreadsheet ROUND(), not Python's round().

    The trade discount is specified as `Round(Current * 0.9, 0)` in a Google
    Sheet, where 22.5 rounds to 23. Python's round() is banker's rounding and
    gives 22, which would silently disagree with the commissioner's own
    numbers on every contract landing on a half-dollar.
    """
    return math.floor(value + 0.5)


def escalate(contract: Contract, season: int, rules: ContractRules) -> Contract:
    """Apply the post-season salary increase (14.2).

    Rookie-protected players are exempt for the duration of their protection
    (7.3) -- which is verifiable in the league's records: Bhayshul Tuten sits
    at $1 for 2026 while every other minimum contract escalated to $6.
    """
    if contract.is_rookie_protected(season):
        return contract
    return replace(contract, salary=contract.salary + rules.annual_escalation)


def franchise_tag_salary(salary: int, rules: ContractRules) -> int:
    """Salary after applying the franchise tag (6.2).

    Deliberately not floored at zero: the league's records show tags landing
    at $0 (Mahomes, 2025) and even -$2 (Edwards, 2024), where a negative
    salary acts as cap credit. Flooring here would quietly disagree with how
    the commissioner has actually applied the rule.
    """
    return salary - rules.franchise_discount


def can_franchise_tag(
    contract: Contract, season: int, rules: ContractRules, *, prior_salary: int | None = None
) -> tuple[bool, str]:
    """Whether the tag may be applied, and why not if it may not (6.1, 6.3).

    `prior_salary` is the player's previous-season salary, which is what 6.1
    actually tests. When omitted it is inferred by undoing this year's
    escalation -- correct for any player who was on the roster last season,
    which is every player the tag can apply to anyway.
    """
    if contract.franchise_tagged_season == season - 1:
        return False, "tagged last season; 6.3 bars consecutive years"

    if rules.franchise_max_prior_salary is not None:
        if prior_salary is None:
            prior_salary = contract.salary - rules.annual_escalation
        if prior_salary > rules.franchise_max_prior_salary:
            return False, (
                f"previous-season salary ${prior_salary} exceeds the "
                f"${rules.franchise_max_prior_salary} limit in 6.1"
            )
    return True, ""


def apply_franchise_tag(contract: Contract, season: int, rules: ContractRules) -> Contract:
    return replace(
        contract,
        salary=franchise_tag_salary(contract.salary, rules),
        franchise_tagged_season=season,
    )


def trade_salary(salary: int, rules: ContractRules) -> int:
    """Salary for the receiving team after the one-time discount (10.2)."""
    return _round_half_up(salary * rules.trade_discount)


def can_rookie_protect(contract: Contract, rules: ContractRules) -> tuple[bool, str]:
    """Whether a just-drafted rookie may be designated (7.1, 7.2).

    Only checks the properties of the contract itself; the two-at-a-time
    limit (7.4.2) is a roster-level constraint, see `rookie_protection_slots`.
    """
    if contract.salary > rules.rookie_protection_max_salary:
        return False, (
            f"salary ${contract.salary} exceeds the "
            f"${rules.rookie_protection_max_salary} limit in 7.2"
        )
    return True, ""


def apply_rookie_protection(contract: Contract, season: int, rules: ContractRules) -> Contract:
    """Protect a rookie for his rookie season plus one more (7.3)."""
    return replace(
        contract,
        rookie_protected_through=season + rules.rookie_protection_seasons - 1,
    )


def rookie_protection_slots(
    contracts: list[Contract], season: int, rules: ContractRules
) -> int:
    """How many further rookies this roster may protect (7.4.2)."""
    in_use = sum(1 for c in contracts if c.is_rookie_protected(season))
    return max(0, rules.max_rookie_protections - in_use)


def steal_keep_price(offer: int, salary: int, rules: ContractRules) -> int:
    """What the current owner pays to keep a player under a steal offer (15.4).

        keep = ceil((offer - salary) * 0.85 + salary)

    The defender absorbs 85% of the premium, so keeping is never free -- which
    is the whole point of the mechanic.
    """
    return math.ceil((offer - salary) * rules.steal_keep_factor + salary)


def min_offer_to_pry(salary: int, market_value: float, rules: ContractRules) -> int:
    """Smallest offer that makes keeping cost more than the player is worth.

    Solves `steal_keep_price(offer) > market_value` by search rather than
    algebraically, so the ceiling in the keep-price formula is respected
    exactly instead of approximated.

    Note the consequence: because the defender only pays 85 cents on the
    dollar, prying a player loose always costs the attacker *more* than the
    player's market value. Against a rational, cap-healthy owner a steal
    cannot generate surplus -- its value lies in cap-squeezed defenders and in
    the salary damage a *refused* steal still inflicts.
    """
    offer = max(salary, rules.min_bid)  # 15.5: the offer must be >= current salary
    while steal_keep_price(offer, salary, rules) <= market_value:
        offer += 1
    return offer


def cap_damage_if_kept(offer: int, salary: int, rules: ContractRules) -> int:
    """Extra salary the defender carries if he keeps the player at this offer.

    A refused steal is not a wasted pick: in a league where nine of twelve
    teams are over the cap, forcing a rival to absorb more salary has real
    competitive value.
    """
    return steal_keep_price(offer, salary, rules) - salary
