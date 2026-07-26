"""Snake-order math and live pick tracking, shared by manual entry and Sleeper sync.

Team indices are 0-indexed everywhere in this module; `LeagueSettings.draft_slot`
is 1-indexed (the user-facing convention), so `DraftState.my_team_index`
converts once at the boundary.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from data.models import LeagueSettings


def round_number(overall_pick: int, num_teams: int) -> int:
    return (overall_pick - 1) // num_teams + 1


def pick_in_round(overall_pick: int, num_teams: int) -> int:
    """0-indexed position within the round."""
    return (overall_pick - 1) % num_teams


def snake_team_index(round_num: int, pos_in_round: int, num_teams: int) -> int:
    """0-indexed team picking at `pos_in_round` of `round_num`, reversing on even rounds."""
    return pos_in_round if round_num % 2 == 1 else num_teams - 1 - pos_in_round


def team_index_on_the_clock(overall_pick: int, num_teams: int) -> int:
    """0-indexed team on the clock for `overall_pick` in a keeperless snake draft."""
    return snake_team_index(
        round_number(overall_pick, num_teams), pick_in_round(overall_pick, num_teams), num_teams
    )


def overall_pick_for_team(round_num: int, team_index: int, num_teams: int) -> int:
    """Inverse of `team_index_on_the_clock`: the overall pick number for a given round/team."""
    if round_num < 1:
        raise ValueError(f"round_num must be >= 1, got {round_num}")
    if not (0 <= team_index < num_teams):
        raise ValueError(f"team_index must be in [0, {num_teams}), got {team_index}")
    pos = team_index if round_num % 2 == 1 else num_teams - 1 - team_index
    return (round_num - 1) * num_teams + pos + 1


def build_pick_schedule(league: LeagueSettings) -> list[tuple[int, int]]:
    """The draft's actual running order as (team_index, round) per pick.

    Standard snake order, minus any (team, round) slot a keeper has already
    consumed. Because teams may keep different numbers of players, the order
    is no longer a pure function of the pick number -- team 5 forfeiting its
    third-rounder shifts everyone after it -- so the schedule is materialized
    once here and every "who is on the clock" question reads from it.

    With no keepers this reproduces plain snake order exactly.
    """
    forfeited = {(k.team_slot - 1, k.round) for k in league.keepers}

    schedule: list[tuple[int, int]] = []
    for round_num in range(1, league.rounds + 1):
        for pos in range(league.num_teams):
            team_index = snake_team_index(round_num, pos, league.num_teams)
            if (team_index, round_num) not in forfeited:
                schedule.append((team_index, round_num))
    return schedule


@dataclass(frozen=True)
class Pick:
    overall_pick: int
    round: int
    pick_in_round: int
    team_index: int
    player_id: str
    timestamp: str


@dataclass
class DraftState:
    league: LeagueSettings
    pick_history: list[Pick] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._schedule = build_pick_schedule(self.league)

    @property
    def schedule(self) -> list[tuple[int, int]]:
        """(team_index, round) for every pick in the draft, keeper holes removed."""
        return self._schedule

    @property
    def total_picks(self) -> int:
        return len(self._schedule)

    @property
    def next_overall_pick(self) -> int:
        return len(self.pick_history) + 1

    @property
    def is_complete(self) -> bool:
        return len(self.pick_history) >= self.total_picks

    def _scheduled(self, overall_pick: int) -> tuple[int, int] | None:
        """The (team_index, round) slotted for a 1-indexed overall pick, or None past the end."""
        if not (1 <= overall_pick <= len(self._schedule)):
            return None
        return self._schedule[overall_pick - 1]

    @property
    def on_the_clock_team_index(self) -> int | None:
        """Team the schedule expects to pick next, or None once the draft is done.

        Read from the materialized schedule rather than recomputed from the
        pick number, so keeper-forfeited picks are skipped correctly. Note
        this reflects the *schedule*: recording a pick with an explicit
        `team_index` (an out-of-order or traded pick) does not shift it.
        """
        slot = self._scheduled(self.next_overall_pick)
        return slot[0] if slot else None

    @property
    def current_round(self) -> int | None:
        slot = self._scheduled(self.next_overall_pick)
        return slot[1] if slot else None

    @property
    def my_team_index(self) -> int:
        return self.league.draft_slot - 1

    def is_drafted(self, player_id: str) -> bool:
        return any(p.player_id == player_id for p in self.pick_history)

    def record_pick(self, player_id: str, team_index: int | None = None) -> Pick:
        if self.is_drafted(player_id):
            raise ValueError(f"{player_id} has already been drafted")
        if team_index is not None and not (0 <= team_index < self.league.num_teams):
            raise ValueError(f"team_index must be in [0, {self.league.num_teams}), got {team_index}")

        overall = self.next_overall_pick
        slot = self._scheduled(overall)
        if slot is None:
            raise ValueError(
                f"draft is complete: all {self.total_picks} scheduled picks have been made"
            )
        scheduled_team, round_num = slot

        pick = Pick(
            overall_pick=overall,
            round=round_num,
            pick_in_round=pick_in_round(overall, self.league.num_teams),
            team_index=team_index if team_index is not None else scheduled_team,
            player_id=player_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self.pick_history.append(pick)
        return pick

    def undo_last_pick(self) -> Pick | None:
        if not self.pick_history:
            return None
        return self.pick_history.pop()

    def picks_until_my_turn(self, count: int = 2) -> list[int]:
        """Picks remaining before each of my next `count` turns (0 = on the clock now).

        Returns fewer than `count` entries when the draft has that few of my
        turns left.
        """
        start = self.next_overall_pick
        result: list[int] = []
        for overall in range(start, len(self._schedule) + 1):
            if len(result) == count:
                break
            if self._schedule[overall - 1][0] == self.my_team_index:
                result.append(overall - start)
        return result

    def my_remaining_picks(self) -> int:
        return sum(
            1
            for overall in range(self.next_overall_pick, len(self._schedule) + 1)
            if self._schedule[overall - 1][0] == self.my_team_index
        )

    def roster_player_ids(self, team_index: int) -> list[str]:
        return [p.player_id for p in self.pick_history if p.team_index == team_index]

    def to_dict(self) -> dict:
        return {"picks": [asdict(p) for p in self.pick_history]}

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: str | Path, league: LeagueSettings) -> "DraftState":
        raw = json.loads(Path(path).read_text())
        picks = [Pick(**p) for p in raw["picks"]]
        return cls(league=league, pick_history=picks)
