"""Multi-year contract value under annual salary escalation.

In a redraft league a contract is worth `market_value - salary` and the
question ends there. Here every retained contract gains $5 a season (14.2),
so its surplus decays by $5 a year even if the player never declines. Two
consequences drive most dynasty decisions in this league:

- **Expensive veterans decay fastest in relative terms.** A $60 contract worth
  $60 today is worth $55 against next year's market, then $50.
- **Rookie protection is worth far more than it looks.** Two seasons exempt
  from escalation *and* from steal attempts (7.3), on a contract capped at $30
  (7.2), in a league where every other contract inflates. With both slots free
  it is the cheapest edge in the rulebook.

Player aging is deliberately *not* modelled here. The roster and ranking
sources carry no birth dates, and inventing an age curve would dress up a
guess as analysis. Instead the caller supplies expected market value per
season; `flat_market` and `decaying_market` are crude stand-ins until a source
with ages is wired in.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence

from data.models import Contract, ContractRules


@dataclass(frozen=True)
class SeasonValue:
    season: int
    salary: int
    market_value: float
    discount: float

    @property
    def surplus(self) -> float:
        return self.market_value - self.salary

    @property
    def discounted_surplus(self) -> float:
        return self.surplus * self.discount


@dataclass(frozen=True)
class ContractValuation:
    contract: Contract
    seasons: tuple[SeasonValue, ...]

    @property
    def current_surplus(self) -> float:
        """This season's surplus alone -- the redraft view."""
        return self.seasons[0].surplus if self.seasons else 0.0

    @property
    def total_value(self) -> float:
        """Discounted surplus across the whole horizon -- the dynasty view."""
        return sum(s.discounted_surplus for s in self.seasons)


def flat_market(market_value: float, horizon: int) -> tuple[float, ...]:
    """Hold market value constant. Neutral on aging, honest about knowing nothing."""
    return tuple(market_value for _ in range(horizon))


def decaying_market(market_value: float, horizon: int, decay: float = 0.85) -> tuple[float, ...]:
    """Decline market value by a fixed factor per season.

    A blunt stand-in for an age curve: right in direction for an aging
    veteran, wrong for a 23-year-old still ascending. Use it for the former
    and `flat_market` for the latter until real ages are available.
    """
    return tuple(market_value * decay**year for year in range(horizon))


def value_contract(
    contract: Contract,
    market_by_season: Sequence[float],
    rules: ContractRules,
    season: int,
    *,
    discount_rate: float = 0.6,
) -> ContractValuation:
    """Value a contract across a horizon, applying escalation and protection.

    `discount_rate` weights future seasons: 0.6 means next year counts 60% of
    this year. Lower it to weight winning now, raise it toward 1.0 for a
    rebuild. It is the single knob that turns this engine from win-now to
    dynasty, which is why it is a parameter and not a constant.
    """
    seasons = []
    salary = contract.salary
    for year, market in enumerate(market_by_season):
        current = season + year
        if year > 0 and not contract.is_rookie_protected(current):
            salary += rules.annual_escalation
        seasons.append(
            SeasonValue(
                season=current,
                salary=salary,
                market_value=market,
                discount=discount_rate**year,
            )
        )
    return ContractValuation(contract=contract, seasons=tuple(seasons))


def rookie_protection_premium(
    salary: int,
    market_by_season: Sequence[float],
    rules: ContractRules,
    season: int,
    *,
    discount_rate: float = 0.6,
) -> float:
    """Extra discounted surplus rookie protection buys, versus the same contract unprotected.

    Quantifies the escalation exemption only. The steal immunity that comes
    with it (7.3) is worth more still and is not priced here -- so treat this
    as a floor on the tag's value, not an estimate of it.
    """
    protected = Contract(
        player_name="", salary=salary,
        rookie_protected_through=season + rules.rookie_protection_seasons - 1,
    )
    plain = Contract(player_name="", salary=salary)
    return (
        value_contract(protected, market_by_season, rules, season, discount_rate=discount_rate).total_value
        - value_contract(plain, market_by_season, rules, season, discount_rate=discount_rate).total_value
    )
