import pytest

from data.models import Keeper, Player, Position
from data.name_matching import (
    KeeperResolutionError,
    match_players,
    normalize_name,
    resolve_keepers,
    resolve_one,
)


def _player(name, position=Position.WR, team="KC"):
    return Player(
        player_id=name.lower().replace(" ", "-"),
        name=name,
        nfl_team=team,
        position=position,
        eligible_positions=frozenset({position}),
    )


@pytest.fixture
def players():
    return [
        _player("Ja'Marr Chase", Position.WR, "CIN"),
        _player("Justin Jefferson", Position.WR, "MIN"),
        _player("Amon-Ra St Brown", Position.WR, "DET"),
        _player("Jahmyr Gibbs", Position.RB, "DET"),
        _player("Bijan Robinson", Position.RB, "ATL"),
        _player("AJ Brown", Position.WR, "NE"),
    ]


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("A.J. Brown Jr.", "aj brown"),
        ("Ja'Marr Chase", "jamarr chase"),
        ("Amon-Ra  St Brown", "amonra st brown"),
        ("Patrick Mahomes II", "patrick mahomes"),
    ],
)
def test_normalize_name_strips_punctuation_and_suffixes(raw, expected):
    assert normalize_name(raw) == expected


def test_matches_on_partial_surname(players):
    assert resolve_one("jefferson", players).name == "Justin Jefferson"


def test_matches_through_punctuation(players):
    assert resolve_one("jamarr chase", players).name == "Ja'Marr Chase"


def test_matches_hyphenated_name_typed_plainly(players):
    assert resolve_one("amon ra st brown", players).name == "Amon-Ra St Brown"


def test_match_players_returns_ranked_candidates(players):
    matches = match_players("brown", players, limit=3)
    assert matches
    assert all(isinstance(score, (int, float)) for _, score in matches)
    scores = [score for _, score in matches]
    assert scores == sorted(scores, reverse=True)


def test_bare_shared_surname_is_treated_as_ambiguous(players):
    """"brown" alone genuinely could be either Brown; recording the wrong
    player mid-draft costs more than asking which one was meant."""
    assert resolve_one("brown", players) is None
    assert {p.name for p, _ in match_players("brown", players)} >= {
        "AJ Brown",
        "Amon-Ra St Brown",
    }


def test_gibberish_matches_nothing(players):
    assert resolve_one("zzzzqqq", players) is None
    assert match_players("zzzzqqq", players) == []


def test_empty_query_matches_nothing(players):
    assert match_players("   ", players) == []
    assert resolve_one("", players) is None


def test_resolve_keepers_maps_names_to_ids(players):
    keepers = (
        Keeper(team_slot=1, player_name="Bijan Robinson", round=2),
        Keeper(team_slot=3, player_name="jefferson", round=1),
    )
    resolved = resolve_keepers(keepers, players)
    assert resolved["Bijan Robinson"] == "bijan-robinson"
    assert resolved["jefferson"] == "justin-jefferson"


def test_unmatchable_keeper_raises_with_suggestions(players):
    keepers = (Keeper(team_slot=1, player_name="Totally Unknown Guy", round=1),)
    with pytest.raises(KeeperResolutionError, match="did not match exactly one player"):
        resolve_keepers(keepers, players)


def test_no_keepers_resolves_to_empty(players):
    assert resolve_keepers((), players) == {}
