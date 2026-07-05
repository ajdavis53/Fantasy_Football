import pytest

from config.settings import LeagueConfigError, load_league_settings
from data.models import Position


def test_load_league_settings_from_fixture(test_league):
    assert test_league.num_teams == 4
    assert test_league.draft_slot == 2
    assert test_league.bench_offsets[Position.RB] == 2
    flex_slot = test_league.roster_slots.flex_slots()[0]
    assert flex_slot.eligible_positions == frozenset({Position.RB, Position.WR, Position.TE})


def test_missing_required_key_raises(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("name: Bad League\nnum_teams: 10\n")
    with pytest.raises(LeagueConfigError):
        load_league_settings(path)


def test_draft_slot_out_of_range_raises(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        "name: Bad\nnum_teams: 4\ndraft_slot: 9\n"
        "roster_slots:\n  - name: QB\n    positions: [QB]\n    count: 1\n"
        "scoring:\n  pass_yd: 0.04\n"
    )
    with pytest.raises(LeagueConfigError):
        load_league_settings(path)


def test_bool_count_rejected(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        "name: Bad\nnum_teams: 4\ndraft_slot: 1\n"
        "roster_slots:\n  - name: QB\n    positions: [QB]\n    count: true\n"
        "scoring:\n  pass_yd: 0.04\n"
    )
    with pytest.raises(LeagueConfigError):
        load_league_settings(path)


def test_non_integer_bench_offset_rejected(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        "name: Bad\nnum_teams: 4\ndraft_slot: 1\n"
        "roster_slots:\n  - name: QB\n    positions: [QB]\n    count: 1\n"
        "scoring:\n  pass_yd: 0.04\n"
        "bench_offsets:\n  QB: 2.9\n"
    )
    with pytest.raises(LeagueConfigError):
        load_league_settings(path)


def test_invalid_position_in_roster_slot_raises(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        "name: Bad\nnum_teams: 4\ndraft_slot: 1\n"
        "roster_slots:\n  - name: QB\n    positions: [ZZ]\n    count: 1\n"
        "scoring:\n  pass_yd: 0.04\n"
    )
    with pytest.raises(LeagueConfigError):
        load_league_settings(path)
