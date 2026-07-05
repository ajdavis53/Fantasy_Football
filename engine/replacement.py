"""Generalized replacement-level baselines for any roster construction.

Works for any mix of dedicated and FLEX-eligible slots (single FLEX, multiple
FLEX, SUPERFLEX, etc.) by allocating FLEX capacity to whichever positions
have the best remaining value, rather than assuming a fixed split.
"""
from __future__ import annotations

from dataclasses import dataclass

from data.models import LeagueSettings, Position


@dataclass(frozen=True)
class PlayerValue:
    player_id: str
    position: Position
    value: float


def _group_by_position_sorted(player_values: list[PlayerValue]) -> dict[Position, list[PlayerValue]]:
    by_position: dict[Position, list[PlayerValue]] = {}
    for pv in player_values:
        by_position.setdefault(pv.position, []).append(pv)
    for pos in by_position:
        by_position[pos].sort(key=lambda pv: pv.value, reverse=True)
    return by_position


def compute_effective_starters(
    player_values: list[PlayerValue], league: LeagueSettings
) -> dict[Position, int]:
    """Per-position starter count after allocating FLEX capacity by best remaining value."""
    by_position = _group_by_position_sorted(player_values)

    effective_starters: dict[Position, int] = {p: 0 for p in Position}
    for slot in league.roster_slots.dedicated_slots():
        for pos in slot.eligible_positions:
            effective_starters[pos] += league.num_teams * slot.count

    # Flex slots are allocated in the order they appear in league.roster_slots,
    # greedily claiming the best remaining value per slot -- this is a
    # sequential heuristic, not a joint optimization across slots. When two
    # flex slots share eligible positions (e.g. FLEX and SUPERFLEX both
    # include RB), list the more exclusive/scarce-position slot first in the
    # league YAML (e.g. SUPERFLEX before FLEX) so it claims its priority
    # position before a broader flex slot competes for the same players.
    for slot in league.roster_slots.flex_slots():
        pool: list[PlayerValue] = []
        for pos in slot.eligible_positions:
            already_claimed = effective_starters.get(pos, 0)
            pool.extend(by_position.get(pos, [])[already_claimed:])
        pool.sort(key=lambda pv: pv.value, reverse=True)

        take = league.num_teams * slot.count
        for pv in pool[:take]:
            effective_starters[pv.position] += 1

    return effective_starters


def _value_at_rank(sorted_players: list[PlayerValue], rank: int) -> float:
    """`rank` is 1-indexed; ranks beyond the pool clamp to its last player.

    `rank <= 0` means zero roster demand at this position (no slot
    references it at all) and returns a 0.0 baseline, rather than clamping
    up to the #1 player -- crediting the whole pool's value as "above
    replacement" instead of understating it against the best player.
    """
    if not sorted_players or rank <= 0:
        return 0.0
    index = min(rank - 1, len(sorted_players) - 1)
    return sorted_players[index].value


def compute_replacement_baselines(
    player_values: list[PlayerValue], league: LeagueSettings
) -> dict[Position, dict[str, float]]:
    """Per position: {"VOLS": value of the last starter, "VORP": value at last-starter + bench offset}."""
    by_position = _group_by_position_sorted(player_values)
    effective_starters = compute_effective_starters(player_values, league)

    baselines: dict[Position, dict[str, float]] = {}
    for pos, players in by_position.items():
        vols_rank = effective_starters.get(pos, 0)
        vorp_rank = vols_rank + league.bench_offsets.get(pos, 0)
        baselines[pos] = {
            "VOLS": _value_at_rank(players, vols_rank),
            "VORP": _value_at_rank(players, vorp_rank),
        }
    return baselines
