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
        # periods and apostrophes sit inside a name part, so they vanish
        ("A.J. Brown Jr.", "aj brown"),
        ("Ja'Marr Chase", "jamarr chase"),
        # hyphens join two parts, so they become a space and both stay matchable
        ("Amon-Ra  St Brown", "amon ra st brown"),
        ("Jaxon Smith-Njigba", "jaxon smith njigba"),
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


def test_matches_half_of_a_hyphenated_name(players):
    """"amon ra" is exactly the sort of half-remembered name this exists for.

    Deleting the hyphen instead of splitting on it collapses the target to
    "amonra", which shares no token with the query and scores 54 -- so this
    match failed silently before.
    """
    assert resolve_one("amon ra", players).name == "Amon-Ra St Brown"


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


def test_a_fully_typed_name_always_resolves(players):
    """The margin rule must not reject a perfectly typed name.

    "Bijan Robinson" and "Brian Robinson" share a surname and differ by two
    letters in the forename, so a full, correct entry scores 100 against one
    and low-90s against the other -- a margin under 15. Asking "did you mean
    Bijan Robinson?" when the user typed exactly that is the wrong failure.
    """
    roster = players + [_player("Brian Robinson", Position.RB, "ATL")]
    assert resolve_one("bijan robinson", roster).name == "Bijan Robinson"
    assert resolve_one("Bijan Robinson", roster).name == "Bijan Robinson"


def test_two_players_sharing_a_name_stay_ambiguous(players):
    roster = players + [_player("AJ Brown", Position.WR, "PHI")]
    assert resolve_one("aj brown", roster) is None
