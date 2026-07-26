"""V1 pick recommendations: value over replacement, adjusted for roster need.

Deliberately heuristic and explainable. Under a pick clock the useful output
is not a single number but a short ranked list you can scan, each row saying
why it is there -- "best value left", "last of his tier", "you still need a
TE". Opponent simulation (real VONA and survival probabilities) is a later
phase; the `likely_gone` flag here is a deterministic worst-case stand-in.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from data.models import LeagueSettings, Position
from engine.draft_state import DraftState
from engine.replacement import PlayerValue, compute_effective_starters

# Multipliers applied to VORP by how badly the roster still needs the position.
UNFILLED_STARTER_BOOST = 1.25
UNFILLED_FLEX_BOOST = 1.08
POSITION_FILLED_DISCOUNT = 0.82

# How much the starter boost escalates per pick of slack lost. A flat boost is
# not enough on its own: a low-VORP position (QB in a league with three flex
# spots) never out-scores the RB/WR pool, so a purely greedy drafter reaches
# the final round with the slot still empty and fields an illegal lineup.
URGENCY_RAMP = 0.35
URGENCY_WINDOW = 5

# Diminishing returns on stacking one position. Without it the deepest, highest
# -VORP position wins every bench pick and the roster ends up absurdly lopsided
# (eleven receivers), because a flat "already filled" discount still leaves that
# position ahead of everything else every single round.
DEPTH_DECAY = 0.88
FREE_BACKUPS = 1

# Beyond its startable slots, a position is worth this many bench bodies before
# further copies are useless. A hard cap is needed as well as the decay above:
# late in a draft the deep positions have all fallen below replacement while a
# shallow one (DEF, K) is still nominally above its own baseline, so raw VORP
# happily recommends an eighth defense. You can only ever start one.
BACKUP_ALLOWANCE = 1


@dataclass
class Recommendation:
    player_id: str
    name: str
    position: str
    team: str | None
    vorp: float
    score: float
    tier: int | None
    adp: float | None
    rank_diff: float | None
    reasons: list[str] = field(default_factory=list)


def _dedicated_requirements(league: LeagueSettings) -> dict[Position, int]:
    required: dict[Position, int] = {}
    for slot in league.roster_slots.dedicated_slots():
        for position in slot.eligible_positions:
            required[position] = required.get(position, 0) + slot.count
    return required


def _flex_capacity(league: LeagueSettings) -> tuple[int, frozenset[Position]]:
    total = 0
    eligible: set[Position] = set()
    for slot in league.roster_slots.flex_slots():
        total += slot.count
        eligible.update(slot.eligible_positions)
    return total, frozenset(eligible)


def roster_gaps(
    state: DraftState, league: LeagueSettings, position_by_id: dict[str, Position]
) -> tuple[dict[Position, int], int]:
    """How many dedicated starter slots, and how many flex slots, I still need.

    Dedicated slots are filled first, and only the players left over count
    toward flex -- otherwise a roster of three RBs would look like it had
    already covered a flex spot it still needs a body for.
    """
    counts: dict[Position, int] = {}
    for player_id in state.roster_player_ids(state.my_team_index):
        position = position_by_id.get(player_id)
        if position is not None:
            counts[position] = counts.get(position, 0) + 1

    unfilled: dict[Position, int] = {}
    leftover: dict[Position, int] = dict(counts)
    for position, required in _dedicated_requirements(league).items():
        have = leftover.get(position, 0)
        used = min(have, required)
        unfilled[position] = required - used
        leftover[position] = have - used

    flex_total, flex_eligible = _flex_capacity(league)
    spare = sum(count for position, count in leftover.items() if position in flex_eligible)
    return unfilled, max(0, flex_total - spare)


def _urgency(slack: int) -> float:
    """Escalation factor for an unfilled starter slot, given picks of slack.

    `slack` is how many picks I have beyond the number of starter slots still
    to fill. While it is comfortable the need boost stays gentle; as it runs
    down the boost climbs, so a cheap-but-required position gets taken before
    it is too late rather than being crowded out every round.
    """
    if slack >= URGENCY_WINDOW:
        return 1.0
    return 1.0 + (URGENCY_WINDOW - max(slack, 0)) * URGENCY_RAMP


def position_capacity(league: LeagueSettings, board: list[dict]) -> dict[Position, int]:
    """Most copies of each position worth rostering: what a team starts, plus a backup.

    Derived from the same league-wide flex allocation the replacement
    baselines use, so flex capacity is shared out by actual value rather than
    credited in full to every eligible position. Handing all three flex slots
    to RB *and* WR *and* TE implies a ceiling of five tight ends, which no one
    drafts.
    """
    values = [
        PlayerValue(
            player_id=row["player_id"],
            position=Position(row["position"]),
            value=row.get("points", row["vorp"]),
        )
        for row in board
    ]
    effective = compute_effective_starters(values, league)

    capacity: dict[Position, int] = {}
    for position, league_wide in effective.items():
        if league_wide <= 0:
            continue
        per_team = math.ceil(league_wide / league.num_teams)
        capacity[position] = per_team + BACKUP_ALLOWANCE
    return capacity


def _depth_penalty(position: Position, held: int, league: LeagueSettings) -> float:
    """Decay for piling up a position past its starting slots plus a backup."""
    startable = _dedicated_requirements(league).get(position, 0)
    surplus = max(0, held - startable - FREE_BACKUPS)
    return DEPTH_DECAY**surplus


def _need_multiplier(
    position: Position,
    unfilled: dict[Position, int],
    flex_needed: int,
    flex_eligible: frozenset[Position],
    slack: int,
    held: int,
    league: LeagueSettings,
) -> tuple[float, str | None]:
    if unfilled.get(position, 0) > 0:
        return (
            UNFILLED_STARTER_BOOST * _urgency(slack),
            f"need {unfilled[position]} more starting {position.value}",
        )

    penalty = _depth_penalty(position, held, league)
    if flex_needed > 0 and position in flex_eligible:
        return (
            UNFILLED_FLEX_BOOST * _urgency(slack) * penalty,
            f"fills one of {flex_needed} open FLEX",
        )
    return POSITION_FILLED_DISCOUNT * penalty, None


def recommend(
    state: DraftState,
    board: list[dict],
    league: LeagueSettings,
    top_n: int = 12,
) -> list[Recommendation]:
    """Rank the best available picks right now.

    `board` is the precomputed VBD board (see scripts/build_board.py): rows
    carrying player_id, name, position, vorp, tier, adp and rank_diff.
    """
    available = [row for row in board if not state.is_drafted(row["player_id"])]
    if not available:
        return []

    position_by_id = {row["player_id"]: Position(row["position"]) for row in board}
    unfilled, flex_needed = roster_gaps(state, league, position_by_id)
    _, flex_eligible = _flex_capacity(league)

    held: dict[Position, int] = {}
    for player_id in state.roster_player_ids(state.my_team_index):
        position = position_by_id.get(player_id)
        if position is not None:
            held[position] = held.get(position, 0) + 1

    def fills_a_gap(position: Position) -> bool:
        return unfilled.get(position, 0) > 0 or (
            flex_needed > 0 and position in flex_eligible
        )

    # Drop positions already stocked to capacity. Once everything is capped the
    # remaining bench spots go to flex-eligible positions -- extra skill-player
    # depth covers byes and injuries, whereas a fourth defense never plays.
    capacity = position_capacity(league, board)
    within_capacity = [
        row
        for row in available
        if held.get(Position(row["position"]), 0)
        < capacity.get(Position(row["position"]), 0)
    ]
    if within_capacity:
        available = within_capacity
    else:
        flex_only = [row for row in available if Position(row["position"]) in flex_eligible]
        if flex_only:
            available = flex_only

    # Once picks left equals starter slots left, every remaining pick has to
    # fill one, so bench depth stops being an option entirely.
    starters_needed = sum(unfilled.values()) + flex_needed
    slack = state.my_remaining_picks() - starters_needed
    if slack <= 0 and starters_needed > 0:
        forced = [row for row in available if fills_a_gap(Position(row["position"]))]
        if forced:
            available = forced

    # Who is the last man in his tier at his position -- i.e. taking someone
    # else means the next player there is a step down, not a lateral move.
    remaining_in_tier: dict[tuple[str, int], int] = {}
    for row in available:
        if row.get("tier") is not None:
            key = (row["position"], row["tier"])
            remaining_in_tier[key] = remaining_in_tier.get(key, 0) + 1

    # Deterministic stand-in for VONA: assume every intervening team takes the
    # best remaining player, so anything inside that many picks is likely gone.
    # Only worth saying when it separates the options -- early in a round with
    # twenty picks to wait it is true of everything shown, and a flag on every
    # row is noise rather than a signal.
    turns = state.picks_until_my_turn(1)
    picks_until_next_turn = turns[0] if turns else 0
    flag_likely_gone = 0 < picks_until_next_turn < top_n

    recommendations: list[Recommendation] = []
    for index, row in enumerate(available):
        position = Position(row["position"])
        multiplier, need_reason = _need_multiplier(
            position, unfilled, flex_needed, flex_eligible, slack, held.get(position, 0), league
        )

        reasons: list[str] = []
        if need_reason:
            reasons.append(need_reason)

        tier = row.get("tier")
        if tier is not None and remaining_in_tier.get((row["position"], tier)) == 1:
            reasons.append(f"last of {row['position']} tier {tier}")

        if row.get("rank_diff") is not None and row["rank_diff"] >= 12:
            reasons.append(f"market lets him fall (+{row['rank_diff']:.0f} vs ADP)")

        if flag_likely_gone and index < picks_until_next_turn:
            reasons.append("unlikely to last to your next pick")

        recommendations.append(
            Recommendation(
                player_id=row["player_id"],
                name=row["name"],
                position=row["position"],
                team=row.get("team"),
                vorp=row["vorp"],
                score=round(row["vorp"] * multiplier, 1),
                tier=tier,
                adp=row.get("adp"),
                rank_diff=row.get("rank_diff"),
                reasons=reasons,
            )
        )

    recommendations.sort(key=lambda r: r.score, reverse=True)
    return recommendations[:top_n]
