"""Market-clearing auction prices for a keeper league.

Published auction values (ETR's, for instance) are computed for a *from-
scratch* draft: every team starts empty, the whole cap chases the whole
player pool, and the values sum to exactly `teams x cap` because they are an
allocation of that money. ETR's Half PPR column sums to $2,400 -- 12 x $200 --
for precisely this reason.

A keeper league breaks both halves of that assumption. Most of the money is
already committed to contracts, and most of the players are already owned, so
the auction is a much smaller market than the one the published values
describe. Rescaling those values by `cap_a / cap_b` does not fix it: applying
1.5x to FFL-NY's 2026 rosters implies a league-wide surplus of -$680, which a
closed market cannot produce.

The fix is to re-solve rather than rescale. Take the published values only as
an opinion about *relative* worth, invert them back to a value-over-
replacement scale, then re-clear that scale against the dollars and slots the
auction will actually have.

Prices are therefore endogenous: they depend on how much every owner cuts,
which depends on prices. `engine.cuts` closes that loop.
"""
from __future__ import annotations

from dataclasses import dataclass

from engine.replacement import PlayerValue


@dataclass(frozen=True)
class AuctionMarket:
    """A cleared market: what each player costs, given the money and slots."""

    prices: dict[str, float]
    dollars: int
    """Total cap available across every team, after retained salary."""
    slots: int
    """Total roster spots to be filled across every team."""
    min_bid: int

    @property
    def discretionary(self) -> int:
        """Money above the unavoidable $1-per-slot floor -- what actually bids up players."""
        return max(0, self.dollars - self.slots * self.min_bid)

    def price(self, player_id: str) -> float:
        return self.prices.get(player_id, float(self.min_bid))

    def surplus(self, player_id: str, salary: int) -> float:
        """Market price less the salary owed: what keeping this contract is worth."""
        return self.price(player_id) - salary


def implied_vorp(
    auction_values: dict[str, float], min_bid: int = 1
) -> dict[str, float]:
    """Invert published auction values back to a value-over-replacement scale.

    A published value is `min_bid + share_of_discretionary_money`, so the part
    above the minimum bid is proportional to value over replacement. Anything
    at or below the minimum is replacement level and inverts to zero.

    This is the fallback path, used when no point projections are available.
    It inherits the publisher's roster assumptions -- their flex count, their
    bench depth -- so it is less accurate than deriving VORP from projected
    points under this league's own settings (`engine.vbd`). Prefer that when
    projections exist; this keeps the engine usable when they do not.
    """
    return {pid: max(0.0, value - min_bid) for pid, value in auction_values.items()}


def clear_market(
    player_values: list[PlayerValue],
    dollars: int,
    slots: int,
    min_bid: int = 1,
) -> AuctionMarket:
    """Distribute `dollars` across `slots` roster spots, in proportion to value.

    Every filled slot costs at least `min_bid`, so that floor comes off the
    top and only the remainder is bid in proportion to value over replacement.
    Players outside the top `slots` price at the minimum: the market will not
    reach them, and pricing them any higher would allocate money that has
    already been spent on better players.
    """
    if slots <= 0 or not player_values:
        return AuctionMarket(
            prices={pv.player_id: float(min_bid) for pv in player_values},
            dollars=max(0, dollars),
            slots=max(0, slots),
            min_bid=min_bid,
        )

    ranked = sorted(player_values, key=lambda pv: pv.value, reverse=True)
    bought = ranked[:slots]
    total_value = sum(max(0.0, pv.value) for pv in bought)
    discretionary = max(0, dollars - slots * min_bid)

    prices = {pv.player_id: float(min_bid) for pv in ranked}
    if total_value > 0 and discretionary > 0:
        for pv in bought:
            prices[pv.player_id] = min_bid + discretionary * max(0.0, pv.value) / total_value

    return AuctionMarket(prices=prices, dollars=dollars, slots=slots, min_bid=min_bid)


def max_affordable_bid(
    remaining_cap: int, slots_to_fill: int, min_bid: int = 1
) -> int:
    """The most a team can bid and still fill its roster at the minimum bid.

    Rule 5.2 requires fielding a full lineup when the auction ends, so every
    remaining slot after this one has to be reserved at `min_bid`. This is the
    number that decides whether an opponent can actually outbid you -- the
    single most useful figure to have on screen during a live auction.
    """
    if slots_to_fill <= 0:
        return 0
    return max(0, remaining_cap - (slots_to_fill - 1) * min_bid)
