from __future__ import annotations

import pytest

from data.models import Contract, ContractRules, Position
from engine.steal import defend_against_steal, evaluate_steal, rank_steal_targets

RULES = ContractRules()


def contract(name, salary, team="rival", protected_through=None):
    return Contract(
        player_name=name, salary=salary, position=Position.WR,
        team=team, rookie_protected_through=protected_through,
    )


def test_defender_keeps_when_the_keep_price_is_below_market():
    result = evaluate_steal(contract("Trey McBride", 14), market_value=38, offer=20, rules=RULES)
    assert result.keep_price == 20  # ceil(6 * 0.85 + 14) = ceil(19.1)
    assert result.defender_keeps


def test_defender_surrenders_once_keeping_costs_more_than_he_is_worth():
    """$43 is the real threshold, not $42.

    At an offer of $42 the keep price is ceil(28 * 0.85 + 14) = 38, landing
    exactly on market value, so an indifferent owner keeps. The ceiling makes
    these boundaries jump by whole dollars, which is why `min_offer_to_pry`
    searches rather than solving the formula algebraically.
    """
    assert evaluate_steal(contract("Trey McBride", 14), 38, 42, RULES).defender_keeps

    result = evaluate_steal(contract("Trey McBride", 14), market_value=38, offer=43, rules=RULES)
    assert result.keep_price == 39 > 38
    assert not result.defender_keeps


def test_a_refused_steal_still_inflicts_cap_damage():
    """The consolation prize: a rival who must already cut absorbs more salary."""
    result = evaluate_steal(contract("Trey McBride", 14), market_value=38, offer=43, rules=RULES)
    assert result.cap_damage_if_kept == result.keep_price - 14 == 25


def test_prying_a_player_loose_never_yields_surplus_against_a_rational_owner():
    result = evaluate_steal(contract("X", 27), market_value=80, offer=90, rules=RULES)
    assert not result.defender_keeps
    assert result.surplus_if_acquired < 0


def test_a_distressed_owner_surrenders_at_a_lower_offer():
    """An owner over the cap values a contract below market, because keeping costs a cut elsewhere."""
    target = contract("Trey McBride", 14)
    healthy = rank_steal_targets([target], lambda c: 38.0, RULES, 2026)
    squeezed = rank_steal_targets(
        [target], lambda c: 38.0, RULES, 2026, defender_discount=lambda c: 0.7
    )
    assert squeezed[0].offer < healthy[0].offer
    assert squeezed[0].surplus_if_acquired > healthy[0].surplus_if_acquired


def test_rookie_protected_players_are_excluded():
    """7.3 exempts them from steal attempts entirely -- do not waste the pick."""
    targets = [
        contract("Emeka Egbuka", 20, protected_through=2026),
        contract("Bhayshul Tuten", 1, protected_through=2026),
        contract("Trey McBride", 14),
    ]
    ranked = rank_steal_targets(targets, lambda c: 38.0, RULES, 2026)
    assert [e.contract.player_name for e in ranked] == ["Trey McBride"]

    # ...and they become fair game once protection lapses
    assert len(rank_steal_targets(targets, lambda c: 38.0, RULES, 2027)) == 3


def test_a_franchise_tag_offers_no_protection():
    """15.2 removed tag protection from steals in 2024."""
    tagged = Contract(player_name="Y", salary=20, position=Position.WR,
                      team="rival", franchise_tagged_season=2026)
    assert len(rank_steal_targets([tagged], lambda c: 40.0, RULES, 2026)) == 1


def test_own_team_is_excluded():
    targets = [contract("mine", 10, team="Andrew's Team"), contract("theirs", 10)]
    ranked = rank_steal_targets(
        targets, lambda c: 30.0, RULES, 2026, exclude_teams=["Andrew's Team"]
    )
    assert [e.contract.player_name for e in ranked] == ["theirs"]


def test_targets_rank_by_surplus_then_cap_damage():
    targets = [contract("cheap", 5), contract("pricey", 40)]
    market = {"cheap": 30.0, "pricey": 45.0}
    ranked = rank_steal_targets(targets, lambda c: market[c.player_name], RULES, 2026)
    assert [e.contract.player_name for e in ranked] == ["pricey", "cheap"]


def test_defence_ladder_finds_the_walk_away_point():
    """Decide the walk-away number before an offer lands, not while it is on the clock."""
    ladder = defend_against_steal(contract("Jameson Williams", 18), market_value=25, rules=RULES)
    worth_keeping = [offer for offer, _, keep in ladder if keep]
    walk_away = max(worth_keeping) + 1

    assert min(offer for offer, _, _ in ladder) == 18  # 15.5 floors the offer at salary
    assert all(k for _, _, k in ladder[: len(worth_keeping)])  # keeping is worth it up to a point
    assert not any(k for _, _, k in ladder[len(worth_keeping):])  # and never again after it
    assert walk_away > 18
