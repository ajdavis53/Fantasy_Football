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


def team_index_on_the_clock(overall_pick: int, num_teams: int) -> int:
    """0-indexed team on the clock for `overall_pick`, accounting for snake reversal."""
    r = round_number(overall_pick, num_teams)
    pos = pick_in_round(overall_pick, num_teams)
    return pos if r % 2 == 1 else num_teams - 1 - pos


def overall_pick_for_team(round_num: int, team_index: int, num_teams: int) -> int:
    """Inverse of `team_index_on_the_clock`: the overall pick number for a given round/team."""
    if round_num < 1:
        raise ValueError(f"round_num must be >= 1, got {round_num}")
    if not (0 <= team_index < num_teams):
        raise ValueError(f"team_index must be in [0, {num_teams}), got {team_index}")
    pos = team_index if round_num % 2 == 1 else num_teams - 1 - team_index
    return (round_num - 1) * num_teams + pos + 1


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

    @property
    def next_overall_pick(self) -> int:
        return len(self.pick_history) + 1

    @property
    def on_the_clock_team_index(self) -> int:
        """Which team the standard snake order expects to pick next.

        Derived purely from `next_overall_pick`, not from `pick_history`'s
        recorded `team_index` values -- an out-of-order/traded pick (recorded
        via `record_pick(..., team_index=...)`) does not shift this or
        `picks_until_my_turn`. Reconciling trades into turn prediction is not
        yet supported.
        """
        return team_index_on_the_clock(self.next_overall_pick, self.league.num_teams)

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
        resolved_team_index = (
            team_index if team_index is not None else self.on_the_clock_team_index
        )
        pick = Pick(
            overall_pick=overall,
            round=round_number(overall, self.league.num_teams),
            pick_in_round=pick_in_round(overall, self.league.num_teams),
            team_index=resolved_team_index,
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
        """How many picks occur before each of my next `count` turns, counting from now (0 = my turn right now)."""
        start = self.next_overall_pick
        result: list[int] = []
        overall = start
        while len(result) < count:
            if team_index_on_the_clock(overall, self.league.num_teams) == self.my_team_index:
                result.append(overall - start)
            overall += 1
        return result

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
