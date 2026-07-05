import pytest

from engine.vbd import compute_vbd


def test_vorp_matches_value_minus_baseline(test_league, sample_player_values):
    vbd = compute_vbd(sample_player_values, test_league, baseline="VORP")

    assert vbd["qb0"] == pytest.approx(100 - 60)
    assert vbd["rb0"] == pytest.approx(120 - 60)
    assert vbd["wr0"] == pytest.approx(115 - 55)
    assert vbd["te0"] == pytest.approx(90 - 50)


def test_vols_matches_value_minus_baseline(test_league, sample_player_values):
    vbd = compute_vbd(sample_player_values, test_league, baseline="VOLS")

    assert vbd["qb0"] == pytest.approx(100 - 70)
    assert vbd["rb0"] == pytest.approx(120 - 70)
    assert vbd["wr0"] == pytest.approx(115 - 75)
    assert vbd["te0"] == pytest.approx(90 - 90)


def test_vbd_covers_every_player(test_league, sample_player_values):
    vbd = compute_vbd(sample_player_values, test_league)
    assert set(vbd.keys()) == {pv.player_id for pv in sample_player_values}


def test_invalid_baseline_name_raises(test_league, sample_player_values):
    with pytest.raises(ValueError):
        compute_vbd(sample_player_values, test_league, baseline="vorp")
