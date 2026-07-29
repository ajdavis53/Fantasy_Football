from __future__ import annotations

import pytest

from data.models import Contract, ContractRules, Position
from engine.roster_plan import plan_roster, taggable

RULES = ContractRules(salary_cap=100, max_roster=3, min_roster=1)


def contract(name, salary, team="T", tagged=None):
    return Contract(
        player_name=name, salary=salary, position=Position.WR,
        team=team, franchise_tagged_season=tagged,
    )


def prices(mapping):
    return lambda c: mapping[c.player_name]


def test_tags_the_contract_where_ten_dollars_buys_the_most():
    """Only one player carries surplus, so the tag belongs on him."""
    roster = [contract("bargain", 18), contract("dud", 40)]
    plan = plan_roster(roster, prices({"bargain": 25, "dud": 5}), RULES, 2026)

    assert [t.contract.player_name for t in plan.tags] == ["bargain"]
    assert plan.tags[0].original_salary == 18
    assert plan.tags[0].tagged_salary == 8
    assert plan.tags[0].gain == pytest.approx(10)
    assert plan.surplus == pytest.approx(17)


def test_a_tag_can_make_a_contract_worth_keeping():
    """Priced $5 under salary, the $10 discount flips it to a keep."""
    roster = [contract("marginal", 30)]
    untagged = plan_roster(roster, prices({"marginal": 25}), RULES, 2026, tags_available=0)
    tagged = plan_roster(roster, prices({"marginal": 25}), RULES, 2026)

    assert untagged.keep == ()
    assert [c.player_name for c in tagged.keep] == ["marginal"]
    assert tagged.salary == 20


def test_never_spends_a_tag_on_a_player_it_then_cuts():
    """A $10 discount cannot rescue a contract priced $30 under water."""
    plan = plan_roster([contract("hopeless", 40)], prices({"hopeless": 10}), RULES, 2026)
    assert plan.tags == ()
    assert plan.keep == ()


def test_no_tag_when_none_is_available():
    roster = [contract("bargain", 18)]
    plan = plan_roster(roster, prices({"bargain": 25}), RULES, 2026, tags_available=0)
    assert plan.tags == ()
    assert plan.salary == 18


def test_tag_relieves_the_cap_and_lets_another_contract_survive():
    """The discount is not just surplus -- it is $10 of cap that buys a keep.

    Both contracts have to sit under 6.1's $30 previous-season ceiling to be
    taggable at all, so the cap has to be tight for it to bind here.
    """
    tight = ContractRules(salary_cap=60, max_roster=3, min_roster=1)
    roster = [contract("a", 35), contract("b", 30)]
    price = prices({"a": 45, "b": 40})

    without = plan_roster(roster, price, tight, 2026, tags_available=0)
    with_tag = plan_roster(roster, price, tight, 2026)

    assert len(without.keep) == 1  # 35 + 30 breaks the $60 cap
    assert len(with_tag.keep) == 2  # 25 + 30 fits
    assert with_tag.salary == 55


def test_respects_the_prior_salary_ceiling():
    """6.1 bars tagging a player whose previous-season salary was over $30."""
    roster = [contract("expensive", 86), contract("cheap", 18)]
    plan = plan_roster(roster, prices({"expensive": 200, "cheap": 25}), RULES, 2026)

    assert [t.contract.player_name for t in plan.tags] == ["cheap"]
    assert "expensive" in {c.player_name for c, _ in plan.rejected_tags}


def test_reports_why_a_tag_was_blocked():
    roster = [contract("repeat", 20, tagged=2025), contract("pricey", 86)]
    plan = plan_roster(roster, prices({"repeat": 60, "pricey": 300}), RULES, 2026)

    reasons = {c.player_name: reason for c, reason in plan.rejected_tags}
    assert "6.3" in reasons["repeat"]
    assert "6.1" in reasons["pricey"]


def test_the_prior_salary_ceiling_can_be_disabled():
    """Whether 6.1 binds in 2026 is an open question, so it must be a toggle."""
    unlimited = ContractRules(salary_cap=100, max_roster=3, min_roster=1,
                              franchise_max_prior_salary=None)
    roster = [contract("expensive", 86)]
    plan = plan_roster(roster, prices({"expensive": 95}), unlimited, 2026)
    assert [t.contract.player_name for t in plan.tags] == ["expensive"]
    assert plan.salary == 76


def test_a_second_tag_is_used_when_held():
    """Owners who lost a player to a steal hold two (15.6)."""
    roster = [contract("a", 20), contract("b", 22)]
    price = prices({"a": 25, "b": 26})
    plan = plan_roster(roster, price, RULES, 2026, tags_available=2)

    assert len(plan.tags) == 2
    assert plan.salary == 22  # (20-10) + (22-10)


def test_tags_available_is_capped_by_the_rulebook():
    roster = [contract(n, 20) for n in "abcd"]
    price = prices({n: 30 for n in "abcd"})
    plan = plan_roster(roster, price, RULES, 2026, tags_available=99)
    assert len(plan.tags) <= RULES.max_franchise_tags


def test_taggable_splits_eligible_from_blocked():
    roster = [contract("ok", 18), contract("repeat", 20, tagged=2025), contract("pricey", 86)]
    eligible, blocked = taggable(roster, 2026, RULES)

    assert [c.player_name for c in eligible] == ["ok"]
    assert [c.player_name for c, _ in blocked] == ["repeat", "pricey"]


def test_plan_exposes_budget_and_slots():
    plan = plan_roster([contract("bargain", 18)], prices({"bargain": 25}), RULES, 2026)
    assert plan.bid_budget(RULES) == 92  # 100 cap less the $8 tagged salary
    assert plan.slots_to_fill(RULES) == 2


def test_empty_roster_is_not_an_error():
    plan = plan_roster([], prices({}), RULES, 2026)
    assert plan.keep == () and plan.tags == ()
