"""Steal-round evaluation, from both sides of the offer.

A steal offer forces the current owner to choose: surrender the player at the
offer price, or keep him at `((offer - salary) * 0.85) + salary`. Because the
defender only pays 85 cents on each dollar of premium, prying a player loose
always costs the attacker more than the player is worth. Against a rational,
cap-healthy owner, a steal cannot generate surplus.

That does not make the pick worthless -- it relocates where its value comes
from:

1. **Distressed defenders.** An owner already over the cap has to shed salary
   anyway, so surrendering a player is relief rather than loss, and he lets go
   below the theoretical threshold.
2. **Refused offers still land.** Keeping raises the defender's salary by 85%
   of the premium. Against a rival who must already cut, that is real damage.

So the ranking here scores both outcomes rather than assuming acquisition.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from data.contracts import cap_damage_if_kept, min_offer_to_pry, steal_keep_price
from data.models import Contract, ContractRules


@dataclass(frozen=True)
class StealEvaluation:
    contract: Contract
    market_value: float
    offer: int
    keep_price: int
    defender_keeps: bool
    """Whether a defender valuing the player at `defender_value` would keep him."""
    surplus_if_acquired: float
    """Market value less the offer. Negative when prying costs above market."""
    cap_damage_if_kept: int
    """Salary the defender absorbs by keeping -- the consolation prize."""

    @property
    def pry_cost(self) -> int:
        """What the offer costs above the player's market value."""
        return max(0, self.offer - round(self.market_value))


def evaluate_steal(
    contract: Contract,
    market_value: float,
    offer: int,
    rules: ContractRules,
    *,
    defender_value: float | None = None,
) -> StealEvaluation:
    """Score one offer on one player.

    `defender_value` is what the *current owner* thinks the player is worth,
    which is not always market value: an owner $80 over the cap facing forced
    cuts effectively values a contract below market, because keeping it costs
    him a cut elsewhere. Pass a discounted figure to model that.
    """
    if defender_value is None:
        defender_value = market_value
    keep = steal_keep_price(offer, contract.salary, rules)
    return StealEvaluation(
        contract=contract,
        market_value=market_value,
        offer=offer,
        keep_price=keep,
        defender_keeps=keep <= defender_value,
        surplus_if_acquired=market_value - offer,
        cap_damage_if_kept=cap_damage_if_kept(offer, contract.salary, rules),
    )


def rank_steal_targets(
    contracts: Sequence[Contract],
    market_value_of: Callable[[Contract], float],
    rules: ContractRules,
    season: int,
    *,
    defender_discount: Callable[[Contract], float] | None = None,
    exclude_teams: Sequence[str] = (),
) -> list[StealEvaluation]:
    """Rank every stealable contract in the league at its pry price.

    Rookie-protected players are dropped outright: rule 7.3 exempts them from
    steal attempts entirely, and a franchise tag has offered no protection
    since 2024 (15.2), so protection is the only shield that matters.

    Ordered by retained surplus, then by the cap damage a refusal inflicts --
    so a target that cannot be won cheaply still ranks by how much it hurts
    the owner to keep.
    """
    excluded = set(exclude_teams)
    evaluations = []
    for contract in contracts:
        if contract.team in excluded or not contract.is_steal_eligible(season):
            continue
        market = market_value_of(contract)
        defender = market * (defender_discount(contract) if defender_discount else 1.0)
        offer = min_offer_to_pry(contract.salary, defender, rules)
        evaluations.append(
            evaluate_steal(contract, market, offer, rules, defender_value=defender)
        )

    evaluations.sort(
        key=lambda e: (e.surplus_if_acquired, e.cap_damage_if_kept), reverse=True
    )
    return evaluations


def defend_against_steal(
    contract: Contract,
    market_value: float,
    rules: ContractRules,
    *,
    max_offer: int | None = None,
) -> list[tuple[int, int, bool]]:
    """Your own side of the round: (offer, keep_price, worth_keeping) by offer.

    Walking the ladder in advance matters because the steal round runs in a
    single day over group text -- you want the walk-away number decided before
    an offer arrives, not while it is on the clock.
    """
    ceiling = max_offer if max_offer is not None else max(contract.salary * 3, contract.salary + 30)
    ladder = []
    for offer in range(max(contract.salary, rules.min_bid), ceiling + 1):
        keep = steal_keep_price(offer, contract.salary, rules)
        ladder.append((offer, keep, keep <= market_value))
    return ladder
