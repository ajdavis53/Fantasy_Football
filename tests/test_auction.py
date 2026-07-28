from __future__ import annotations

import pytest

from data.models import Position
from engine.auction import clear_market, implied_vorp, max_affordable_bid
from engine.replacement import PlayerValue


def values(*specs: tuple[str, float], position: Position = Position.RB) -> list[PlayerValue]:
    return [PlayerValue(player_id=pid, position=position, value=v) for pid, v in specs]


def test_prices_sum_to_the_money_available():
    """A cleared market allocates every dollar -- that is what clearing means."""
    pool = values(("a", 100), ("b", 60), ("c", 40), ("d", 0))
    market = clear_market(pool, dollars=200, slots=4)
    assert sum(market.prices.values()) == pytest.approx(200)


def test_this_is_how_published_auction_values_are_built():
    """ETR's Half PPR column sums to exactly $2,400 = 12 teams x $200.

    Re-clearing an inverted set of values at the same money and slots must
    reproduce the originals, which is what makes `implied_vorp` a valid
    inversion rather than an approximation.
    """
    published = {"a": 60.0, "b": 40.0, "c": 20.0, "d": 1.0}
    pool = [
        PlayerValue(player_id=pid, position=Position.RB, value=v)
        for pid, v in implied_vorp(published).items()
    ]
    market = clear_market(pool, dollars=int(sum(published.values())), slots=len(published))
    for pid, original in published.items():
        assert market.price(pid) == pytest.approx(original)


def test_every_filled_slot_costs_at_least_the_minimum_bid():
    market = clear_market(values(("a", 100), ("b", 0), ("c", 0)), dollars=10, slots=3)
    assert min(market.prices.values()) >= 1
    assert market.price("a") > market.price("b")


def test_players_beyond_the_slot_count_price_at_the_minimum():
    """The market never reaches them; pricing them higher spends money twice."""
    market = clear_market(values(("a", 100), ("b", 80), ("c", 60)), dollars=100, slots=2)
    assert market.price("c") == 1
    assert market.price("a") > market.price("b") > 1


def test_price_scales_with_available_money_not_with_the_cap():
    """The same players in a poorer market are cheaper -- prices are endogenous.

    This is why rescaling published values by a cap ratio is the wrong
    transformation for a keeper league.
    """
    pool = values(("a", 100), ("b", 50))
    rich = clear_market(pool, dollars=300, slots=2)
    poor = clear_market(pool, dollars=60, slots=2)
    assert rich.price("a") > poor.price("a")
    assert rich.discretionary == 298
    assert poor.discretionary == 58


def test_no_money_above_the_floor_leaves_everyone_at_minimum():
    market = clear_market(values(("a", 100), ("b", 50)), dollars=2, slots=2)
    assert market.prices == {"a": 1.0, "b": 1.0}


def test_zero_slots_prices_everyone_at_minimum():
    market = clear_market(values(("a", 100)), dollars=500, slots=0)
    assert market.price("a") == 1.0


def test_empty_pool_is_not_an_error():
    assert clear_market([], dollars=100, slots=5).prices == {}


def test_implied_vorp_floors_replacement_level_at_zero():
    assert implied_vorp({"a": 30.0, "b": 1.0, "c": 0.0}) == {"a": 29.0, "b": 0.0, "c": 0.0}


def test_surplus_is_price_less_salary():
    market = clear_market(values(("a", 100), ("b", 50)), dollars=160, slots=2)
    assert market.surplus("a", 50) == pytest.approx(market.price("a") - 50)


@pytest.mark.parametrize(
    "cap,slots,expected",
    [
        (300, 14, 287),   # must reserve $1 for each of the other 13 spots
        (300, 1, 300),    # last slot: everything is bidable
        (50, 5, 46),
        (10, 20, 0),      # already unable to fill the roster
        (100, 0, 0),
    ],
)
def test_max_affordable_bid(cap, slots, expected):
    assert max_affordable_bid(cap, slots) == expected
