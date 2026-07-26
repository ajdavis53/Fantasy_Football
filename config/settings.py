"""Load a league's YAML config into a validated `LeagueSettings`."""
from __future__ import annotations

from pathlib import Path

import yaml

from data.models import Keeper, LeagueSettings, Position, RosterSlot, RosterSlots, ScoringRules


class LeagueConfigError(ValueError):
    pass


def _parse_positions(raw: list[str], slot_name: str) -> frozenset[Position]:
    try:
        return frozenset(Position(p) for p in raw)
    except ValueError as exc:
        valid = ", ".join(p.value for p in Position)
        raise LeagueConfigError(
            f"roster slot {slot_name!r} has an invalid position in {raw!r}; valid positions are {valid}"
        ) from exc


def _parse_roster_slots(raw: list[dict]) -> RosterSlots:
    if not raw:
        raise LeagueConfigError("roster_slots must not be empty")

    slots = []
    seen_names = set()
    for entry in raw:
        try:
            name = entry["name"]
            positions = entry["positions"]
            count = entry["count"]
        except KeyError as exc:
            raise LeagueConfigError(f"roster slot entry {entry!r} is missing required key {exc}") from exc

        if name in seen_names:
            raise LeagueConfigError(f"duplicate roster slot name: {name!r}")
        seen_names.add(name)

        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise LeagueConfigError(f"roster slot {name!r} must have a positive integer count, got {count!r}")

        slots.append(RosterSlot(name=name, eligible_positions=_parse_positions(positions, name), count=count))

    return RosterSlots(slots=tuple(slots))


def _parse_bench_offsets(raw: dict | None) -> dict[Position, int]:
    if not raw:
        return {}
    try:
        positions = {Position(pos): offset for pos, offset in raw.items()}
    except ValueError as exc:
        valid = ", ".join(p.value for p in Position)
        raise LeagueConfigError(f"bench_offsets has an invalid position; valid positions are {valid}") from exc

    result: dict[Position, int] = {}
    for pos, offset in positions.items():
        if isinstance(offset, bool) or not isinstance(offset, int):
            raise LeagueConfigError(f"bench_offsets[{pos.value}] must be an integer, got {offset!r}")
        result[pos] = offset
    return result


def _parse_keepers(raw: list | None, num_teams: int, rounds: int) -> tuple[Keeper, ...]:
    if not raw:
        return ()

    keepers = []
    claimed: dict[tuple[int, int], str] = {}
    for entry in raw:
        try:
            team_slot = entry["team_slot"]
            player_name = entry["player"]
            round_num = entry["round"]
        except (KeyError, TypeError) as exc:
            raise LeagueConfigError(
                f"keeper entry {entry!r} needs 'team_slot', 'player' and 'round'"
            ) from exc

        if isinstance(team_slot, bool) or not isinstance(team_slot, int) or not (1 <= team_slot <= num_teams):
            raise LeagueConfigError(
                f"keeper {player_name!r} has team_slot {team_slot!r}; expected an integer in [1, {num_teams}]"
            )
        if isinstance(round_num, bool) or not isinstance(round_num, int) or not (1 <= round_num <= rounds):
            raise LeagueConfigError(
                f"keeper {player_name!r} has round {round_num!r}; expected an integer in [1, {rounds}]"
            )

        slot = (team_slot, round_num)
        if slot in claimed:
            raise LeagueConfigError(
                f"team {team_slot} has two keepers costing round {round_num}: "
                f"{claimed[slot]!r} and {player_name!r} -- a team can only forfeit that pick once"
            )
        claimed[slot] = player_name
        keepers.append(Keeper(team_slot=team_slot, player_name=player_name, round=round_num))

    return tuple(keepers)


def load_league_settings(path: str | Path) -> LeagueSettings:
    path = Path(path)
    with path.open() as f:
        raw = yaml.safe_load(f)

    if not raw:
        raise LeagueConfigError(f"{path} is empty")

    required = ("name", "num_teams", "draft_slot", "roster_slots", "scoring")
    missing = [key for key in required if key not in raw]
    if missing:
        raise LeagueConfigError(f"{path} is missing required key(s): {', '.join(missing)}")

    num_teams = raw["num_teams"]
    if not isinstance(num_teams, int) or num_teams < 2:
        raise LeagueConfigError(f"num_teams must be an integer >= 2, got {num_teams!r}")

    draft_slot = raw["draft_slot"]
    if not isinstance(draft_slot, int) or not (1 <= draft_slot <= num_teams):
        raise LeagueConfigError(f"draft_slot must be an integer in [1, {num_teams}], got {draft_slot!r}")

    roster_slots = _parse_roster_slots(raw["roster_slots"])
    scoring = ScoringRules(points_per_stat=dict(raw["scoring"]))
    bench_offsets = _parse_bench_offsets(raw.get("bench_offsets"))
    keepers = _parse_keepers(raw.get("keepers"), num_teams, roster_slots.roster_size())

    return LeagueSettings(
        name=raw["name"],
        num_teams=num_teams,
        roster_slots=roster_slots,
        scoring=scoring,
        draft_slot=draft_slot,
        bench_offsets=bench_offsets,
        keepers=keepers,
        league_id=raw.get("league_id"),
        draft_id=raw.get("draft_id"),
    )
