"""Keeper handling: forfeited picks punch holes in the draft order."""
import dataclasses

import pytest

from config.settings import LeagueConfigError, load_league_settings
from data.models import Keeper
from engine.draft_state import DraftState, build_pick_schedule


@pytest.fixture
def league_4x3(test_league):
    """4 teams; test_league.yaml's roster is 6 spots, so 6 rounds of 4 = 24 picks."""
    return test_league


def _with_keepers(league, keepers):
    return dataclasses.replace(league, keepers=tuple(keepers))


def test_schedule_without_keepers_is_plain_snake(league_4x3):
    schedule = build_pick_schedule(league_4x3)
    assert len(schedule) == league_4x3.num_teams * league_4x3.rounds

    teams_round1 = [team for team, rnd in schedule if rnd == 1]
    teams_round2 = [team for team, rnd in schedule if rnd == 2]
    assert teams_round1 == [0, 1, 2, 3]
    assert teams_round2 == [3, 2, 1, 0]


def test_keeper_removes_exactly_that_teams_pick(league_4x3):
    league = _with_keepers(league_4x3, [Keeper(team_slot=3, player_name="Kept Guy", round=2)])
    schedule = build_pick_schedule(league)

    assert len(schedule) == league_4x3.num_teams * league_4x3.rounds - 1
    assert (2, 2) not in schedule  # team_slot 3 -> index 2, round 2
    assert [t for t, r in schedule if r == 2] == [3, 1, 0]
    assert [t for t, r in schedule if r == 1] == [0, 1, 2, 3]


def test_uneven_keeper_counts_shift_later_picks(league_4x3):
    """Teams keeping different numbers is the case that breaks formula-based
    snake math: after the holes, pick N no longer implies a team."""
    league = _with_keepers(
        league_4x3,
        [
            Keeper(team_slot=1, player_name="A", round=1),
            Keeper(team_slot=1, player_name="B", round=2),
            Keeper(team_slot=4, player_name="C", round=1),
        ],
    )
    schedule = build_pick_schedule(league)

    assert len(schedule) == league_4x3.num_teams * league_4x3.rounds - 3
    assert schedule[0] == (1, 1)  # teams 0 and 3 both forfeited round 1
    assert [t for t, r in schedule if r == 1] == [1, 2]
    # Round 2 runs 3,2,1,0 and only team 0 forfeited it.
    assert [t for t, r in schedule if r == 2] == [3, 2, 1]


def test_on_the_clock_follows_schedule_past_a_hole(league_4x3):
    league = _with_keepers(league_4x3, [Keeper(team_slot=2, player_name="Kept", round=1)])
    state = DraftState(league=league)

    assert state.on_the_clock_team_index == 0
    state.record_pick("p1")
    # team index 1 forfeited round 1, so team 2 is up rather than team 1
    assert state.on_the_clock_team_index == 2


def test_picks_until_my_turn_skips_my_forfeited_round(league_4x3):
    """draft_slot 2 -> my_team_index 1, which keeps a player costing its round-2
    pick. Round 1 gives me pick 2; round 2 is forfeited, so my next turn is not
    until round 3 -- a formula-based count would wrongly land in round 2."""
    league = _with_keepers(league_4x3, [Keeper(team_slot=2, player_name="Kept", round=2)])
    state = DraftState(league=league)

    # Round 1 is picks 1-4 (mine is 2); round 2 is picks 5-7 (3,2,0 -- no me);
    # round 3 resumes 0,1,... so mine is pick 9.
    assert state.picks_until_my_turn(2) == [1, 8]
    assert [t for t, r in state.schedule if r == 2] == [3, 2, 0]


def test_my_remaining_picks_drops_by_number_of_keepers(league_4x3):
    baseline = DraftState(league=league_4x3).my_remaining_picks()
    league = _with_keepers(
        league_4x3,
        [
            Keeper(team_slot=2, player_name="A", round=1),
            Keeper(team_slot=2, player_name="B", round=3),
        ],
    )
    assert DraftState(league=league).my_remaining_picks() == baseline - 2


def test_recording_past_the_end_of_the_draft_raises(league_4x3):
    league = dataclasses.replace(league_4x3, keepers=())
    state = DraftState(league=league)
    for i in range(state.total_picks):
        state.record_pick(f"p{i}")

    assert state.is_complete
    assert state.on_the_clock_team_index is None
    with pytest.raises(ValueError, match="draft is complete"):
        state.record_pick("one_too_many")


def test_pick_records_the_scheduled_round_not_a_derived_one(league_4x3):
    league = _with_keepers(league_4x3, [Keeper(team_slot=1, player_name="Kept", round=1)])
    state = DraftState(league=league)

    picks = [state.record_pick(f"p{i}") for i in range(4)]
    # Round 1 is one pick short, so the 4th pick belongs to round 2.
    assert [p.round for p in picks] == [1, 1, 1, 2]


def test_duplicate_keeper_cost_for_one_team_is_rejected(tmp_path):
    path = tmp_path / "league.yaml"
    path.write_text(
        "name: Bad\nnum_teams: 4\ndraft_slot: 1\n"
        "roster_slots:\n  - name: QB\n    positions: [QB]\n    count: 2\n"
        "scoring:\n  pass_yd: 0.04\n"
        "keepers:\n"
        "  - team_slot: 2\n    player: A\n    round: 1\n"
        "  - team_slot: 2\n    player: B\n    round: 1\n"
    )
    with pytest.raises(LeagueConfigError, match="forfeit that pick once"):
        load_league_settings(path)


@pytest.mark.parametrize("bad_round", [0, 99])
def test_keeper_round_out_of_range_is_rejected(tmp_path, bad_round):
    path = tmp_path / "league.yaml"
    path.write_text(
        "name: Bad\nnum_teams: 4\ndraft_slot: 1\n"
        "roster_slots:\n  - name: QB\n    positions: [QB]\n    count: 2\n"
        "scoring:\n  pass_yd: 0.04\n"
        f"keepers:\n  - team_slot: 2\n    player: A\n    round: {bad_round}\n"
    )
    with pytest.raises(LeagueConfigError, match="expected an integer"):
        load_league_settings(path)


def test_keeper_team_slot_out_of_range_is_rejected(tmp_path):
    path = tmp_path / "league.yaml"
    path.write_text(
        "name: Bad\nnum_teams: 4\ndraft_slot: 1\n"
        "roster_slots:\n  - name: QB\n    positions: [QB]\n    count: 2\n"
        "scoring:\n  pass_yd: 0.04\n"
        "keepers:\n  - team_slot: 9\n    player: A\n    round: 1\n"
    )
    with pytest.raises(LeagueConfigError, match="expected an integer"):
        load_league_settings(path)


def test_real_league_configs_load_with_empty_keepers():
    for path in ("config/leagues/live_league.yaml", "config/leagues/sleeper_league.yaml"):
        league = load_league_settings(path)
        assert league.keepers == ()
        assert build_pick_schedule(league) == build_pick_schedule(league)


def test_real_league_round_counts_match_roster_size():
    live = load_league_settings("config/leagues/live_league.yaml")
    sleeper = load_league_settings("config/leagues/sleeper_league.yaml")
    assert live.rounds == 16  # 1QB 2RB 2WR 1TE 3FLEX + 7 bench
    assert sleeper.rounds == 18  # same + DEF, 8 bench
    assert len(build_pick_schedule(live)) == 12 * 16
    assert len(build_pick_schedule(sleeper)) == 10 * 18
