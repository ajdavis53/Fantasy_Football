from __future__ import annotations

import pytest

from app.store import AuctionStore
from data.models import ContractRules, Position
from engine.live_auction import (
    LiveAuction,
    PlayerInfo,
    StartingPosition,
    par_prices,
)
from engine.replacement import PlayerValue

RULES = ContractRules(salary_cap=100, max_roster=4, min_roster=2)

# id -> (name, position, value over replacement)
POOL = {
    "stud": ("Stud Back", Position.RB, 40.0),
    "good": ("Good Back", Position.RB, 30.0),
    "fine": ("Fine Wideout", Position.WR, 20.0),
    "okay": ("Okay Wideout", Position.WR, 15.0),
    "meh": ("Meh Back", Position.RB, 10.0),
    "spare": ("Spare Arm", Position.QB, 5.0),
    "filler": ("Filler Man", Position.WR, 2.0),
    "scrub": ("Scrub Guy", Position.TE, 1.0),
}


def build(starting=None, my_committed=0, my_count=0) -> LiveAuction:
    players = {pid: PlayerInfo(pid, name, pos) for pid, (name, pos, _) in POOL.items()}
    values = [PlayerValue(pid, pos, v) for pid, (_, pos, v) in POOL.items()]
    teams = starting or [
        StartingPosition("me", my_committed, my_count),
        StartingPosition("you", 0, 0),
    ]
    dollars = sum(RULES.salary_cap - t.committed_salary for t in teams)
    slots = sum(RULES.max_roster - t.roster_count for t in teams)
    return LiveAuction.start(
        RULES, players, par_prices(values, dollars, slots, RULES.min_bid), teams, "me"
    )


# -- recording --------------------------------------------------------------

def test_recording_a_sale_moves_budget_and_slots():
    auction = build()
    auction.record("stud", "you", 40)

    them = auction.status("you")
    assert them.spent == 40
    assert them.budget == 60
    assert them.slots_to_fill == 3
    assert them.filled == 1


def test_a_sold_player_leaves_the_board():
    auction = build()
    auction.record("stud", "you", 40)
    assert "stud" not in {p.player_id for p in auction.available()}


def test_undo_restores_the_previous_state():
    auction = build()
    before = auction.status("you")
    auction.record("stud", "you", 40)
    undone = auction.undo()

    assert undone.player_name == "Stud Back"
    assert auction.status("you") == before
    assert "stud" in {p.player_id for p in auction.available()}


def test_undo_on_an_empty_log_is_harmless():
    assert build().undo() is None


def test_selling_the_same_player_twice_is_rejected():
    auction = build()
    auction.record("stud", "you", 40)
    with pytest.raises(ValueError, match="already been sold"):
        auction.record("stud", "me", 20)


def test_a_sub_minimum_price_is_rejected():
    with pytest.raises(ValueError, match="below the \\$1 minimum"):
        build().record("stud", "me", 0)


def test_an_unknown_team_is_rejected():
    with pytest.raises(ValueError, match="unknown team"):
        build().record("stud", "nobody", 5)


def test_players_already_under_contract_never_appear():
    auction = build()
    auction.rostered_ids.add("stud")
    assert "stud" not in {p.player_id for p in auction.available()}


# -- affordability ----------------------------------------------------------

def test_max_bid_reserves_a_dollar_for_each_remaining_slot():
    """5.2 requires fielding a full lineup, so the last slots cannot be spent."""
    auction = build()
    assert auction.status("me").max_bid == 100 - 3  # four slots to fill


def test_max_bid_is_the_whole_budget_on_the_final_slot():
    auction = build(my_count=3)
    assert auction.status("me").slots_to_fill == 1
    assert auction.status("me").max_bid == 100


def test_a_full_roster_cannot_bid():
    auction = build(my_count=4)
    status = auction.status("me")
    assert status.slots_to_fill == 0 and status.max_bid == 0 and not status.can_bid


def test_committed_salary_reduces_the_budget():
    auction = build(my_committed=70)
    assert auction.status("me").budget == 30


# -- inflation --------------------------------------------------------------

def test_inflation_opens_at_exactly_one():
    """Par is the clearing price of this board, so an untouched market reads 1.0."""
    assert build().inflation() == pytest.approx(1.0)


def test_overpaying_early_makes_everything_later_cheaper():
    auction = build()
    par = auction.adjusted_price("good")
    auction.record("stud", "you", 90)

    assert auction.inflation() < 1.0
    assert auction.adjusted_price("good") < par


def test_bargains_early_make_everything_later_dearer():
    auction = build()
    par = auction.adjusted_price("good")
    auction.record("stud", "you", 1)

    assert auction.inflation() > 1.0
    assert auction.adjusted_price("good") > par


def test_inflation_is_one_when_no_slots_remain():
    auction = build(starting=[StartingPosition("me", 0, 4), StartingPosition("you", 0, 4)])
    assert auction.inflation() == 1.0


def test_adjusted_price_never_falls_below_the_minimum_bid():
    auction = build()
    auction.record("stud", "you", 99)
    assert all(auction.adjusted_price(p.player_id) >= RULES.min_bid for p in auction.available())


# -- advice -----------------------------------------------------------------

def test_advice_flags_who_can_actually_outbid_you():
    auction = build()
    advice = auction.bid_advice("stud")
    assert [team for team, _ in advice.contenders] == ["you"]
    assert advice.contested


def test_a_broke_opponent_is_not_a_contender():
    auction = build()
    auction.record("good", "you", 97)  # leaves 'you' with $3 and 3 slots
    advice = auction.bid_advice("stud")

    assert auction.status("you").max_bid < advice.adjusted
    assert not advice.contested


def test_a_full_opponent_is_not_a_contender():
    auction = build(starting=[StartingPosition("me", 0, 0), StartingPosition("you", 0, 4)])
    assert not auction.bid_advice("stud").contested


def test_walk_away_is_capped_by_what_you_can_afford():
    auction = build(my_committed=90)  # $10 budget, 4 slots -> max bid $7
    advice = auction.bid_advice("stud")

    assert advice.my_max_bid == 7
    assert advice.walk_away == 7
    assert advice.adjusted > advice.walk_away


def test_advice_names_the_next_best_at_the_position():
    """What losing the lot actually costs you, rather than the headline price."""
    advice = build().bid_advice("stud")
    assert advice.next_best.player_id == "good"
    assert advice.next_best_gap == pytest.approx(advice.adjusted - build().adjusted_price("good"))


def test_next_best_gap_falls_back_to_full_price_when_nothing_remains():
    auction = build()
    advice = auction.bid_advice("spare")  # the only QB
    assert advice.next_best is None
    assert advice.next_best_gap == advice.adjusted


def test_board_is_ranked_by_value_and_excludes_sold_players():
    auction = build()
    auction.record("stud", "you", 40)
    board = auction.board()

    assert [a.player.player_id for a in board][:2] == ["good", "fine"]
    assert "stud" not in {a.player.player_id for a in board}


def test_nomination_candidates_skip_the_players_you_want():
    """Nominate what you do not want, while rivals still have money to burn."""
    auction = build()
    protected = 3
    candidates = auction.nomination_candidates(limit=2, protect=protected)

    top = [p.player_id for p in sorted(
        auction.available(), key=lambda p: auction.par[p.player_id], reverse=True)]
    assert [c.player.player_id for c in candidates] == top[protected : protected + 2]


# -- persistence ------------------------------------------------------------

def test_sales_survive_a_restart(tmp_path):
    store = AuctionStore(tmp_path / "auction.db")
    auction = build()
    for player, team, price in [("stud", "you", 40), ("good", "me", 25)]:
        store.append(auction.record(player, team, price))

    revived = build()
    revived.replay(AuctionStore(tmp_path / "auction.db").load())

    assert [s.player_id for s in revived.sales] == ["stud", "good"]
    assert revived.status("me").spent == 25
    assert revived.status("you").budget == 60


def test_store_pop_mirrors_undo(tmp_path):
    store = AuctionStore(tmp_path / "auction.db")
    auction = build()
    store.append(auction.record("stud", "you", 40))
    store.append(auction.record("good", "me", 25))

    auction.undo()
    store.pop()

    assert [s.player_id for s in store.load()] == ["stud"]


def test_store_round_trips_position_and_price(tmp_path):
    store = AuctionStore(tmp_path / "auction.db")
    store.append(build().record("stud", "you", 40))
    (sale,) = store.load()

    assert sale.position is Position.RB
    assert sale.price == 40
    assert sale.player_name == "Stud Back"


def test_clear_empties_the_log(tmp_path):
    store = AuctionStore(tmp_path / "auction.db")
    store.append(build().record("stud", "you", 40))
    store.clear()
    assert store.load() == []


def test_replay_renumbers_out_of_order_sequences(tmp_path):
    auction = build()
    sales = [auction.record("stud", "you", 40), auction.record("good", "me", 25)]
    fresh = build()
    fresh.replay(list(reversed(sales)))
    assert [s.sequence for s in fresh.sales] == [0, 1]
    assert [s.player_id for s in fresh.sales] == ["stud", "good"]


def test_next_best_is_the_player_below_not_the_best_alternative():
    """For anyone below the positional leader these differ, and only one is useful.

    Lose the third-best back and you could still buy the best one, so "best
    remaining alternative" is a *better* player and the gap goes negative --
    which answers no question anyone asks at a table. The tier drop does.
    """
    auction = build()
    advice = auction.bid_advice("meh")  # the third RB by value

    assert advice.next_best is None or auction.par[advice.next_best.player_id] <= auction.par["meh"]
    assert advice.next_best_gap >= 0


def test_next_best_gap_is_never_negative_anywhere_on_the_board():
    auction = build()
    assert all(advice.next_best_gap >= 0 for advice in auction.board())


def test_the_positional_leader_points_at_the_runner_up():
    advice = build().bid_advice("stud")
    assert advice.next_best.player_id == "good"
    assert advice.next_best_gap > 0
