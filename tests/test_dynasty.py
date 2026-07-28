from __future__ import annotations

import pytest

from data.models import Contract, ContractRules
from engine.dynasty import (
    decaying_market,
    flat_market,
    rookie_protection_premium,
    value_contract,
)

RULES = ContractRules()


def test_salary_escalates_five_dollars_a_season():
    valuation = value_contract(
        Contract(player_name="X", salary=20), flat_market(40, 3), RULES, 2026
    )
    assert [s.salary for s in valuation.seasons] == [20, 25, 30]
    assert [s.season for s in valuation.seasons] == [2026, 2027, 2028]


def test_surplus_decays_even_when_the_player_does_not():
    """Escalation alone erodes a contract by $5 a year -- the league's core dynasty pressure."""
    valuation = value_contract(
        Contract(player_name="X", salary=20), flat_market(40, 3), RULES, 2026
    )
    assert [s.surplus for s in valuation.seasons] == [20, 15, 10]


def test_current_surplus_is_the_redraft_view():
    valuation = value_contract(
        Contract(player_name="X", salary=20), flat_market(40, 3), RULES, 2026
    )
    assert valuation.current_surplus == 20
    assert valuation.total_value == pytest.approx(20 + 15 * 0.6 + 10 * 0.36)


def test_discount_rate_turns_win_now_into_rebuild():
    """The single knob that reweights the engine between postures."""
    young = Contract(player_name="young", salary=10)
    market = flat_market(30, 4)

    win_now = value_contract(young, market, RULES, 2026, discount_rate=0.2).total_value
    rebuild = value_contract(young, market, RULES, 2026, discount_rate=0.9).total_value
    assert rebuild > win_now


def test_expensive_veterans_lose_value_faster_than_cheap_youth():
    """A $60 contract and a $10 contract both escalate $5, but not equally painfully."""
    market = decaying_market(65, 3, decay=0.8)
    veteran = value_contract(Contract(player_name="vet", salary=60), market, RULES, 2026)

    cheap = value_contract(
        Contract(player_name="kid", salary=10), flat_market(30, 3), RULES, 2026
    )
    assert veteran.total_value < cheap.total_value


def test_rookie_protection_freezes_salary_for_two_seasons():
    protected = Contract(player_name="R", salary=12, rookie_protected_through=2027)
    valuation = value_contract(protected, flat_market(30, 4), RULES, 2026)
    assert [s.salary for s in valuation.seasons] == [12, 12, 17, 22]


def test_rookie_protection_premium_is_positive_and_grows_with_the_horizon():
    short = rookie_protection_premium(12, flat_market(30, 2), RULES, 2026)
    long = rookie_protection_premium(12, flat_market(30, 4), RULES, 2026)
    assert 0 < short <= long


def test_decaying_market_declines_and_flat_market_does_not():
    assert decaying_market(100, 3, decay=0.5) == (100, 50, 25)
    assert flat_market(100, 3) == (100, 100, 100)


def test_empty_horizon_is_not_an_error():
    valuation = value_contract(Contract(player_name="X", salary=20), (), RULES, 2026)
    assert valuation.total_value == 0
    assert valuation.current_surplus == 0
