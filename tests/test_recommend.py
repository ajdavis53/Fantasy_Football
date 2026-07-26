import pytest

from data.models import Position
from engine.draft_state import DraftState
from engine.recommend import recommend, roster_gaps


def _row(player_id, name, position, vorp, tier=1, adp=None, rank_diff=None):
    return {
        "player_id": player_id,
        "name": name,
        "position": position,
        "team": "KC",
        "vorp": vorp,
        "tier": tier,
        "adp": adp,
        "rank_diff": rank_diff,
    }


@pytest.fixture
def board():
    return [
        _row("rb1", "RB One", "RB", 200, tier=1),
        _row("rb2", "RB Two", "RB", 150, tier=2),
        _row("wr1", "WR One", "WR", 180, tier=1),
        _row("wr2", "WR Two", "WR", 140, tier=2),
        _row("qb1", "QB One", "QB", 120, tier=1),
        _row("qb2", "QB Two", "QB", 100, tier=2),
        _row("te1", "TE One", "TE", 110, tier=1),
    ]


@pytest.fixture
def positions(board):
    return {row["player_id"]: Position(row["position"]) for row in board}


def test_roster_gaps_on_empty_roster_reports_all_starters(test_league, positions):
    """test_league.yaml starts 1 QB, 1 RB, 1 WR and 1 RB/WR/TE flex."""
    state = DraftState(league=test_league)
    unfilled, flex_needed = roster_gaps(state, test_league, positions)

    assert unfilled[Position.QB] == 1
    assert unfilled[Position.RB] == 1
    assert unfilled[Position.WR] == 1
    assert flex_needed == 1


def test_dedicated_slots_fill_before_flex(test_league, positions):
    """One RB covers the dedicated RB slot, not the flex -- otherwise the roster
    would look like it had a flex body it still needs."""
    state = DraftState(league=test_league)
    state.record_pick("rb1", team_index=state.my_team_index)

    unfilled, flex_needed = roster_gaps(state, test_league, positions)
    assert unfilled[Position.RB] == 0
    assert flex_needed == 1


def test_second_player_at_a_position_counts_toward_flex(test_league, positions):
    state = DraftState(league=test_league)
    state.record_pick("rb1", team_index=state.my_team_index)
    state.record_pick("rb2", team_index=state.my_team_index)

    unfilled, flex_needed = roster_gaps(state, test_league, positions)
    assert unfilled[Position.RB] == 0
    assert flex_needed == 0


def test_recommendations_are_ranked_by_score(test_league, board):
    state = DraftState(league=test_league)
    recs = recommend(state, board, test_league)
    scores = [r.score for r in recs]
    assert scores == sorted(scores, reverse=True)


def test_drafted_players_are_not_recommended(test_league, board):
    state = DraftState(league=test_league)
    state.record_pick("rb1")
    recs = recommend(state, board, test_league)
    assert "rb1" not in {r.player_id for r in recs}


def test_need_boost_lifts_an_unfilled_position(test_league, board):
    """QB is boosted while the slot is empty and discounted once it is filled.
    QB is not flex-eligible here, so a second QB is pure bench depth."""
    empty = DraftState(league=test_league)
    before = next(r for r in recommend(empty, board, test_league) if r.player_id == "qb1")
    assert before.score > before.vorp

    filled = DraftState(league=test_league)
    filled.record_pick("qb1", team_index=filled.my_team_index)
    after = next(r for r in recommend(filled, board, test_league) if r.player_id == "qb2")
    assert after.score < after.vorp


def test_last_player_in_a_tier_is_flagged(test_league, board):
    state = DraftState(league=test_league)
    rec = next(r for r in recommend(state, board, test_league) if r.player_id == "te1")
    assert any("last of TE tier 1" in reason for reason in rec.reasons)


def test_large_adp_value_is_surfaced(test_league):
    board = [_row("wr9", "Falling WR", "WR", 100, tier=3, adp=60.0, rank_diff=25.0)]
    state = DraftState(league=test_league)
    rec = recommend(state, board, test_league)[0]
    assert any("market lets him fall" in reason for reason in rec.reasons)


def test_last_picks_are_forced_to_fill_required_starters(test_league, board):
    """With only as many picks left as unfilled starter slots, bench depth stops
    being an option. Without this a cheap-but-required position (QB behind a
    deep RB/WR pool) never out-scores the field and the draft ends with an
    illegal lineup."""
    state = DraftState(league=test_league)
    # Fill everything except QB, leaving one pick and one unfilled slot.
    for player_id in ("rb1", "rb2", "wr1", "wr2", "te1"):
        state.record_pick(player_id, team_index=state.my_team_index)

    while state.my_remaining_picks() > 1:
        state.record_pick(f"filler{state.next_overall_pick}", team_index=0)

    recs = recommend(state, board, test_league)
    assert recs, "expected a forced recommendation"
    assert {r.position for r in recs} == {"QB"}


def test_urgency_escalates_as_slack_runs_out():
    from engine.recommend import _urgency

    assert _urgency(10) == 1.0
    assert _urgency(3) > _urgency(4)
    assert _urgency(0) > _urgency(3)


def test_position_capacity_shares_flex_rather_than_duplicating_it(test_league, board):
    """test_league has 1 flex. Crediting it to RB, WR and TE alike would imply
    room for a bench full of each; capacity comes from the league-wide flex
    allocation instead."""
    from engine.recommend import position_capacity

    capacity = position_capacity(test_league, board)
    assert capacity[Position.QB] == 2  # 1 starter + 1 backup, no flex share
    assert sum(capacity[p] for p in (Position.RB, Position.WR, Position.TE)) < 3 * (
        1 + 1 + 1
    )


def test_position_stocked_to_capacity_is_not_recommended(test_league, board):
    state = DraftState(league=test_league)
    for _ in range(2):
        state.record_pick(
            next(
                r["player_id"]
                for r in board
                if r["position"] == "QB" and not state.is_drafted(r["player_id"])
            ),
            team_index=state.my_team_index,
        )

    recs = recommend(state, board, test_league)
    assert "QB" not in {r.position for r in recs}


def _flagged(recs):
    return [r for r in recs if any("unlikely to last" in x for x in r.reasons)]


def test_likely_gone_flag_is_dropped_when_it_applies_to_everything(test_league, board):
    """A warning on every row is noise, so it is suppressed when the wait is
    longer than the list being shown -- true of everything, useful about
    nothing. Here 4 picks separate my turns but only 3 players are shown."""
    state = DraftState(league=test_league)
    state.record_pick("rb1")  # pick 1, team 0
    state.record_pick("wr1")  # pick 2, me (slot 2)

    assert state.picks_until_my_turn(1) == [4]
    assert not _flagged(recommend(state, board, test_league, top_n=3))


def test_likely_gone_flag_appears_when_it_separates_the_options(test_league, board):
    """One pick until my turn: only the very top player is at real risk."""
    state = DraftState(league=test_league)
    assert state.picks_until_my_turn(1) == [1]

    flagged = _flagged(recommend(state, board, test_league, top_n=6))
    assert len(flagged) == 1


def test_empty_board_returns_no_recommendations(test_league):
    state = DraftState(league=test_league)
    assert recommend(state, [], test_league) == []


def test_top_n_is_respected(test_league, board):
    state = DraftState(league=test_league)
    assert len(recommend(state, board, test_league, top_n=2)) == 2
