import pytest

from engine.draft_state import (
    DraftState,
    overall_pick_for_team,
    pick_in_round,
    round_number,
    team_index_on_the_clock,
)


@pytest.mark.parametrize("num_teams", [2, 4, 8, 10, 12, 14])
def test_snake_math_round_trip_is_exhaustive(num_teams):
    for round_num in range(1, 6):
        for team_index in range(num_teams):
            overall = overall_pick_for_team(round_num, team_index, num_teams)
            assert round_number(overall, num_teams) == round_num
            assert team_index_on_the_clock(overall, num_teams) == team_index
            assert 0 <= pick_in_round(overall, num_teams) < num_teams


def test_known_12_team_snake_pattern():
    # Draft slot 5 (1-indexed) = team_index 4: pick 5 in round 1, pick 20 in round 2.
    assert team_index_on_the_clock(5, 12) == 4
    assert team_index_on_the_clock(20, 12) == 4
    assert overall_pick_for_team(1, 4, 12) == 5
    assert overall_pick_for_team(2, 4, 12) == 20


def test_round_reverses_direction_each_round():
    num_teams = 4
    round1_order = [team_index_on_the_clock(p, num_teams) for p in range(1, 5)]
    round2_order = [team_index_on_the_clock(p, num_teams) for p in range(5, 9)]
    assert round1_order == [0, 1, 2, 3]
    assert round2_order == [3, 2, 1, 0]


def test_record_pick_uses_on_the_clock_team_by_default(test_league):
    state = DraftState(league=test_league)
    pick = state.record_pick("player_a")
    assert pick.overall_pick == 1
    assert pick.team_index == 0
    assert state.next_overall_pick == 2


def test_record_pick_rejects_duplicate_player(test_league):
    state = DraftState(league=test_league)
    state.record_pick("player_a")
    with pytest.raises(ValueError):
        state.record_pick("player_a")


def test_undo_last_pick_reverts_state(test_league):
    state = DraftState(league=test_league)
    state.record_pick("player_a")
    undone = state.undo_last_pick()
    assert undone.player_id == "player_a"
    assert state.next_overall_pick == 1
    assert not state.is_drafted("player_a")


def test_undo_on_empty_history_returns_none(test_league):
    state = DraftState(league=test_league)
    assert state.undo_last_pick() is None


def test_picks_until_my_turn(test_league):
    # test_league.yaml: num_teams=4, draft_slot=2 -> my_team_index=1.
    state = DraftState(league=test_league)
    assert state.picks_until_my_turn(2) == [1, 6]


def test_picks_until_my_turn_is_zero_when_on_the_clock(test_league):
    state = DraftState(league=test_league)
    state.record_pick("player_a")  # team_index 0 picks
    assert state.picks_until_my_turn(1) == [0]


def test_roster_player_ids_filters_by_team(test_league):
    state = DraftState(league=test_league)
    state.record_pick("player_a", team_index=0)
    state.record_pick("player_b", team_index=1)
    state.record_pick("player_c", team_index=0)
    assert state.roster_player_ids(0) == ["player_a", "player_c"]
    assert state.roster_player_ids(1) == ["player_b"]


def test_record_pick_rejects_out_of_range_team_index(test_league):
    state = DraftState(league=test_league)
    with pytest.raises(ValueError):
        state.record_pick("player_a", team_index=test_league.num_teams)
    with pytest.raises(ValueError):
        state.record_pick("player_a", team_index=-1)


def test_overall_pick_for_team_rejects_out_of_range_inputs():
    with pytest.raises(ValueError):
        overall_pick_for_team(1, 4, 4)
    with pytest.raises(ValueError):
        overall_pick_for_team(0, 0, 4)


def test_save_and_load_round_trip(test_league, tmp_path):
    state = DraftState(league=test_league)
    state.record_pick("player_a")
    state.record_pick("player_b")

    path = tmp_path / "draft_state.json"
    state.save(path)

    loaded = DraftState.load(path, test_league)
    assert loaded.pick_history == state.pick_history
