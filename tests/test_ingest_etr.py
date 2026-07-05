from pathlib import Path

import pytest

from data.ingest_etr import ETRIngestError, load_etr_rankings, resolve_column_map, slugify_player_id
from data.models import Position

FIXTURE = Path(__file__).parent / "fixtures" / "etr_sample.csv"


def test_load_etr_rankings_counts_and_fields():
    players, rankings = load_etr_rankings(FIXTURE)

    assert len(players) == 14
    assert len(rankings) == 14

    chase = next(p for p in players if p.name == "Ja'Marr Chase")
    assert chase.position == Position.WR
    assert chase.nfl_team == "CIN"

    chase_ranking = next(r for r in rankings if r.player_id == chase.player_id)
    assert chase_ranking.rank == 1
    assert chase_ranking.tier == 1
    assert chase_ranking.projected_points == pytest.approx(320.5)


def test_dst_alias_maps_to_def():
    players, _ = load_etr_rankings(FIXTURE)
    defense = next(p for p in players if p.name == "San Francisco")
    assert defense.position == Position.DEF


def test_player_id_is_stable_and_slugified():
    pid = slugify_player_id("Ja'Marr Chase", "CIN", Position.WR)
    assert pid == "ja-marr-chase-cin-wr"


def test_column_overrides_for_nonstandard_headers(tmp_path):
    csv_path = tmp_path / "custom.csv"
    csv_path.write_text("Overall,FullName,Pos,Squad\n1,Test Player,RB,KC\n")

    players, rankings = load_etr_rankings(
        csv_path,
        column_overrides={"rank": "Overall", "name": "FullName", "position": "Pos", "team": "Squad"},
    )
    assert players[0].name == "Test Player"
    assert rankings[0].rank == 1


def test_missing_required_column_raises():
    with pytest.raises(ETRIngestError):
        resolve_column_map(["Team", "Notes"])


def test_unrecognized_position_raises(tmp_path):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("Rank,Player,Team,Position\n1,Some Guy,KC,ZZ\n")
    with pytest.raises(ETRIngestError):
        load_etr_rankings(csv_path)


def test_duplicate_header_raises(tmp_path):
    csv_path = tmp_path / "dup_header.csv"
    csv_path.write_text("Rank,Player,Rank,Position\n1,Some Guy,2,RB\n")
    with pytest.raises(ETRIngestError):
        load_etr_rankings(csv_path)


def test_duplicate_player_id_raises(tmp_path):
    csv_path = tmp_path / "dup_player.csv"
    csv_path.write_text("Rank,Player,Team,Position\n1,Some Guy,KC,RB\n2,Some Guy,KC,RB\n")
    with pytest.raises(ETRIngestError):
        load_etr_rankings(csv_path)
