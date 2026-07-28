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
    pos_rank: int | None = None
    """Rank within position (ETR's "RB01" -> 1)."""
    adp: float | None = None
    """Average draft position, i.e. where the market actually takes this player."""

    @property
    def rank_diff(self) -> float | None:
        """ADP minus rank: how much later than this source's rank the market drafts them.

        Positive means the source rates the player higher than the market does
        (a value/bargain); negative means the market reaches relative to the
        source (a fade candidate).
        """
        if self.adp is None:
            return None
        return self.adp - self.rank


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


@dataclass(frozen=True)
class Keeper:
    """A player retained before the draft, at the cost of one round's pick.

    `team_slot` is 1-indexed to match `LeagueSettings.draft_slot`. `round` is
    the round whose pick that team forfeits; teams may keep different numbers
    of players, so the draft order ends up with per-team holes.
    """

    team_slot: int
    player_name: str
    round: int


@dataclass(frozen=True)
class ContractRules:
    """A salary-cap league's contract lifecycle, as data rather than code.

    Every constant here is a league rule that gets voted on annually, so they
    belong in config where a rule change is a one-line edit. Defaults are
    FFL-NY's 2026 rules; see `docs/ffl-ny/league-rules.md` for the section
    numbers each one encodes.
    """

    salary_cap: int = 300
    max_roster: int = 14
    playoff_max_roster: int = 15
    min_roster: int = 9
    min_bid: int = 1

    annual_escalation: int = 5
    """Added to every retained player's salary after the season (14.2)."""

    franchise_discount: int = 10
    """Subtracted from salary when the franchise tag is applied (6.2)."""
    franchise_max_prior_salary: int | None = 30
    """Cap on a taggable player's previous-season salary (6.1); None disables.

    Held as a toggle because every 2025 tag in the league's own records
    exceeds it, so whether it binds in 2026 is an open question with the
    commissioner -- not something to hardcode either way.
    """
    max_franchise_tags: int = 2

    trade_discount: float = 0.9
    """One-time-per-season multiplier applied for the receiving team (10.2)."""

    steal_keep_factor: float = 0.85
    """The defender pays this share of a steal offer's premium to keep (15.4)."""

    rookie_protection_seasons: int = 2
    """Rookie season plus one more, exempt from escalation and steals (7.3)."""
    rookie_protection_max_salary: int = 30
    max_rookie_protections: int = 2


@dataclass(frozen=True)
class Contract:
    """One player's salary and the tags attached to it.

    Salary is always whole dollars: every league operation that produces a
    fraction (the trade discount, the steal keep price) specifies its own
    rounding, so a contract never holds a fractional salary.
    """

    player_name: str
    salary: int
    position: Position | None = None
    nfl_team: str | None = None
    team: str | None = None
    """Fantasy team holding the contract."""
    rookie_protected_through: int | None = None
    """Last season (inclusive) of rookie protection, or None."""
    franchise_tagged_season: int | None = None
    """Season a franchise tag was last applied, or None."""

    def is_rookie_protected(self, season: int) -> bool:
        return self.rookie_protected_through is not None and season <= self.rookie_protected_through

    def is_steal_eligible(self, season: int) -> bool:
        """Rookie protection is the only shield; franchise tags stopped protecting in 2024 (15.2)."""
        return not self.is_rookie_protected(season)


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
    keepers: tuple[Keeper, ...] = ()
    contract_rules: ContractRules | None = None
    """Salary-cap lifecycle, for auction leagues. None means a snake league."""
    league_id: str | None = None
    """Sleeper league_id, if this league is API-backed."""
    draft_id: str | None = None
    """Sleeper draft_id, if this league is API-backed."""

    @property
    def rounds(self) -> int:
        """One round per roster spot; keepers consume roster spots and picks alike."""
        return self.roster_slots.roster_size()

    @property
    def is_auction(self) -> bool:
        return self.contract_rules is not None
