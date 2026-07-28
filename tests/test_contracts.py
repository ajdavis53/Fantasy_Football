"""Contract lifecycle, validated against the league's own historical records.

The trade and franchise-tag figures below are taken from the transaction log
in the league's rules spreadsheet, so these are not invented expectations --
they are what the commissioner actually recorded.
"""
from __future__ import annotations

import pytest

from data.contracts import (
    apply_franchise_tag,
    apply_rookie_protection,
    can_franchise_tag,
    can_rookie_protect,
    cap_damage_if_kept,
    escalate,
    franchise_tag_salary,
    min_offer_to_pry,
    rookie_protection_slots,
    steal_keep_price,
    trade_salary,
)
from data.models import Contract, ContractRules

RULES = ContractRules()


# (starting salary, salary recorded for the receiving team) from the trade log
@pytest.mark.parametrize(
    "salary,expected",
    [
        (21, 19), (11, 10), (24, 22), (23, 21), (3, 3), (1, 1),
        (99, 89), (79, 71), (54, 49), (56, 50), (87, 78), (30, 27),
        (26, 23), (53, 48), (20, 18), (14, 13),
    ],
)
def test_trade_discount_matches_league_records(salary, expected):
    assert trade_salary(salary, RULES) == expected


def test_trade_discount_rounds_half_up_not_bankers():
    """B. Robinson at $125 was recorded at $113, not $112.

    125 * 0.9 = 112.5 exactly. Python's round() is banker's rounding and would
    return 112, silently disagreeing with the commissioner on every contract
    landing on a half-dollar.
    """
    assert trade_salary(125, RULES) == 113
    assert round(125 * 0.9) == 112  # what the naive implementation would give


# (salary before tag, salary after) from the 2025 franchise tag table
@pytest.mark.parametrize(
    "salary,expected",
    [(12, 2), (50, 40), (26, 16), (23, 13), (10, 0), (20, 10), (13, 3), (58, 48), (62, 52)],
)
def test_franchise_tag_matches_league_records(salary, expected):
    assert franchise_tag_salary(salary, RULES) == expected


def test_franchise_tag_is_not_floored_at_zero():
    """The league recorded Edwards at -$2 in 2024; a negative salary is cap credit."""
    assert franchise_tag_salary(8, RULES) == -2


def test_escalation_adds_five():
    contract = Contract(player_name="Dak Prescott", salary=17)
    assert escalate(contract, 2026, RULES).salary == 22


def test_rookie_protection_exempts_from_escalation():
    """Bhayshul Tuten sat at $1 for 2026 while every other minimum contract went to $6."""
    protected = Contract(player_name="Bhayshul Tuten", salary=1, rookie_protected_through=2026)
    assert escalate(protected, 2026, RULES).salary == 1
    # ...and resumes escalating once protection lapses
    assert escalate(protected, 2027, RULES).salary == 6


def test_franchise_tag_blocked_in_consecutive_years():
    contract = Contract(player_name="X", salary=20, franchise_tagged_season=2025)
    allowed, reason = can_franchise_tag(contract, 2026, RULES)
    assert not allowed
    assert "6.3" in reason


def test_franchise_tag_blocked_above_prior_salary_limit():
    """Barkley at $86 was $81 last season, over the $30 ceiling in 6.1."""
    allowed, reason = can_franchise_tag(Contract(player_name="Saquon Barkley", salary=86), 2026, RULES)
    assert not allowed
    assert "$81" in reason and "$30" in reason


def test_franchise_tag_allowed_within_limit():
    """Jameson Williams at $18 was $13 last season."""
    allowed, _ = can_franchise_tag(Contract(player_name="Jameson Williams", salary=18), 2026, RULES)
    assert allowed


def test_franchise_tag_limit_can_be_disabled():
    """Every 2025 tag exceeded the limit, so whether it binds is a config question."""
    unlimited = ContractRules(franchise_max_prior_salary=None)
    allowed, _ = can_franchise_tag(Contract(player_name="Saquon Barkley", salary=86), 2026, unlimited)
    assert allowed


def test_apply_franchise_tag_records_the_season():
    tagged = apply_franchise_tag(Contract(player_name="Jameson Williams", salary=18), 2026, RULES)
    assert tagged.salary == 8
    assert tagged.franchise_tagged_season == 2026
    assert not can_franchise_tag(tagged, 2027, RULES)[0]


def test_rookie_protection_spans_two_seasons():
    protected = apply_rookie_protection(Contract(player_name="R", salary=12), 2026, RULES)
    assert protected.is_rookie_protected(2026)
    assert protected.is_rookie_protected(2027)
    assert not protected.is_rookie_protected(2028)


def test_rookie_protection_blocked_above_salary_limit():
    allowed, reason = can_rookie_protect(Contract(player_name="R", salary=31), RULES)
    assert not allowed and "7.2" in reason


def test_rookie_protection_slots_cap_at_two():
    roster = [Contract(player_name=f"r{i}", salary=10, rookie_protected_through=2027) for i in range(2)]
    assert rookie_protection_slots(roster, 2026, RULES) == 0
    assert rookie_protection_slots(roster[:1], 2026, RULES) == 1
    assert rookie_protection_slots([], 2026, RULES) == 2


def test_protected_player_cannot_be_stolen():
    """7.3 exempts protected rookies from steal attempts; a franchise tag does not (15.2)."""
    protected = Contract(player_name="Emeka Egbuka", salary=20, rookie_protected_through=2026)
    tagged = Contract(player_name="Someone", salary=20, franchise_tagged_season=2026)
    assert not protected.is_steal_eligible(2026)
    assert protected.is_steal_eligible(2027)
    assert tagged.is_steal_eligible(2026)


def test_steal_keep_price_rounds_up():
    """ceil((40 - 14) * 0.85 + 14) = ceil(36.1) = 37."""
    assert steal_keep_price(40, 14, RULES) == 37
    assert steal_keep_price(14, 14, RULES) == 14  # an offer at salary costs nothing to match


def test_pry_price_always_exceeds_market_value():
    """The defender pays only 85c per dollar of premium, so prying costs above market.

    This is the structural reason a steal cannot generate surplus against a
    rational, cap-healthy owner.
    """
    for salary, market in [(14, 38), (15, 35), (10, 27), (27, 80), (47, 71)]:
        offer = min_offer_to_pry(salary, market, RULES)
        assert steal_keep_price(offer, salary, RULES) > market
        assert steal_keep_price(offer - 1, salary, RULES) <= market  # minimal
        assert offer > market


def test_pry_price_respects_minimum_offer_rule():
    """15.5: the offer must be at least the player's current salary."""
    assert min_offer_to_pry(50, 5.0, RULES) == 50


def test_cap_damage_is_the_premium_the_defender_absorbs():
    assert cap_damage_if_kept(42, 14, RULES) == steal_keep_price(42, 14, RULES) - 14
