"""Core domain entities shared by every league and every draft mode.

These are plain data holders with no I/O and no league-specific logic --
that logic lives in `engine/`, parameterized by `LeagueSettings` so the same
code serves any league.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Position(str, Enum):
    QB = "QB"
    RB = "RB"
    WR = "WR"
    TE = "TE"
    K = "K"
    DEF = "DEF"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


@dataclass(frozen=True)
class ExternalIds:
    """Cross-platform IDs for one player, used to join data sources."""

    sleeper_id: str | None = None
    gsis_id: str | None = None
    espn_id: str | None = None
    yahoo_id: str | None = None


@dataclass
class Player:
    player_id: str
    name: str
    nfl_team: str | None
    position: Position
    eligible_positions: frozenset[Position]
    bye_week: int | None = None
    external_ids: ExternalIds = field(default_factory=ExternalIds)
    notes: list[str] = field(default_factory=list)

    def is_eligible_for(self, positions: frozenset[Position]) -> bool:
        return bool(self.eligible_positions & positions)


@dataclass
class PlayerRanking:
    """A ranking/tier for one player from one source (e.g. ETR)."""

    player_id: str
    source: str
    rank: int
    tier: int | None
    position: Position
    projected_points: float | None = None


@dataclass(frozen=True)
class ScoringRules:
    """Points awarded per unit of each stat category.

    Keys are stat category names (e.g. "pass_yd", "rec", "rush_td"); values
    are points per unit of that stat. Missing keys score zero.
    """

    points_per_stat: dict[str, float] = field(default_factory=dict)

    def points_for(self, stats: dict[str, float]) -> float:
        return sum(self.points_per_stat.get(stat, 0.0) * amount for stat, amount in stats.items())


@dataclass(frozen=True)
class RosterSlot:
    """One slot type in a roster, e.g. ("RB", {RB}, 2) or ("FLEX", {RB,WR,TE}, 1)."""

    name: str
    eligible_positions: frozenset[Position]
    count: int

    @property
    def is_flex(self) -> bool:
        return len(self.eligible_positions) > 1

    @property
    def is_bench(self) -> bool:
        return self.name.upper() == "BENCH"


@dataclass(frozen=True)
class RosterSlots:
    slots: tuple[RosterSlot, ...]

    def starter_slots(self) -> tuple[RosterSlot, ...]:
        """Slots that count as starters (excludes bench)."""
        return tuple(s for s in self.slots if not s.is_bench)

    def dedicated_slots(self) -> tuple[RosterSlot, ...]:
        return tuple(s for s in self.starter_slots() if not s.is_flex)

    def flex_slots(self) -> tuple[RosterSlot, ...]:
        return tuple(s for s in self.starter_slots() if s.is_flex)

    def bench_size(self) -> int:
        return sum(s.count for s in self.slots if s.is_bench)

    def roster_size(self) -> int:
        return sum(s.count for s in self.slots)


@dataclass
class LeagueSettings:
    name: str
    num_teams: int
    roster_slots: RosterSlots
    scoring: ScoringRules
    draft_slot: int
    """1-indexed position this user picks from in round 1."""
    bench_offsets: dict[Position, int] = field(default_factory=dict)
    """Per-position VORP baseline offset beyond the last starter (tunable)."""
    league_id: str | None = None
    """Sleeper league_id, if this league is API-backed."""
    draft_id: str | None = None
    """Sleeper draft_id, if this league is API-backed."""
