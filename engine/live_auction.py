"""Live auction state: what has sold, what everyone can still spend, what to pay.

Built for one three-hour evening in somebody's living room, where every sale is
typed in by hand while the next player is already being nominated. The design
priorities follow from that: recording a sale is one action, undo is always
available, and every derived figure recomputes from the sale log rather than
being maintained incrementally -- a running total that drifts is worse than no
total at all.

Two numbers do most of the work at the table:

**Inflation.** Pre-draft prices assume the whole pool clears at par. It never
does. When owners overpay early, the money left chases the same players, and
everything still on the board gets cheaper; when they sit on their hands, the
survivors get dearer. So prices are rescaled after every sale by the money and
slots that actually remain.

**Who can still outbid you.** Rule 5.2 forces every owner to field a full
lineup, so each has to reserve $1 per unfilled slot. An owner with $60 and six
slots left cannot bid $60 -- he can bid $55. That gap decides whether a player
is genuinely contested or whether you are bidding against yourself.

Rule 5.7.2 makes this a sequential elimination auction rather than open
outcry: bidding passes clockwise and opting out is *permanent*. You cannot
re-enter on second thoughts, so the walk-away number has to exist before
bidding opens. That is what `bid_advice` is for.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from data.models import ContractRules, Position
from engine.auction import clear_market, max_affordable_bid
from engine.replacement import PlayerValue


def par_prices(
    available: list[PlayerValue], dollars: int, slots: int, min_bid: int = 1
) -> dict[str, float]:
    """Clear the board the auction will actually see.

    Par has to be the clearing price of the *available* pool against the money
    and slots that actually remain -- not the league-wide equilibrium from the
    cut/keep screen, which prices rostered players too and normalizes over a
    different set. Get this wrong and inflation opens at some arbitrary number
    like 2.9, which tells a human at a table nothing at all. Clearing the real
    board makes inflation open at exactly 1.0, so every later reading is a
    direct measure of how the room has behaved.
    """
    return clear_market(available, dollars, slots, min_bid).prices


@dataclass(frozen=True)
class PlayerInfo:
    player_id: str
    name: str
    position: Position | None = None
    nfl_team: str | None = None


@dataclass(frozen=True)
class Sale:
    """One completed auction lot."""

    sequence: int
    player_id: str
    player_name: str
    team: str
    price: int
    position: Position | None = None


@dataclass(frozen=True)
class StartingPosition:
    """A team's post-drop-deadline state, before the auction opens."""

    team: str
    committed_salary: int
    roster_count: int


@dataclass(frozen=True)
class TeamStatus:
    team: str
    budget: int
    filled: int
    slots_to_fill: int
    max_bid: int
    spent: int
    is_me: bool

    @property
    def can_bid(self) -> bool:
        return self.slots_to_fill > 0 and self.max_bid > 0


@dataclass(frozen=True)
class BidAdvice:
    player: PlayerInfo
    par: float
    """Pre-draft equilibrium price."""
    adjusted: float
    """Par rescaled by how the auction has actually gone so far."""
    my_max_bid: int
    walk_away: int
    """The most it is worth paying: market, capped by what you can afford."""
    contenders: tuple[tuple[str, int], ...]
    """Opponents who could outbid the adjusted price, with their ceilings."""
    next_best: PlayerInfo | None
    """The next player *down* the board at this position."""
    next_best_gap: float
    """Drop to that player -- what losing this lot actually costs.

    Deliberately the next one down rather than the best alternative
    available. For anyone below the positional leader those differ: if you
    lose the third-best running back you could still buy the best one, so
    "best alternative" is a *better* player and the gap comes out negative,
    which is both useless at a table and reads as a rendering fault. The
    question worth answering is the tier question -- if this lot goes, what
    does the next one down cost me -- so the gap is never negative.
    """

    @property
    def contested(self) -> bool:
        return bool(self.contenders)


@dataclass
class LiveAuction:
    rules: ContractRules
    players: dict[str, PlayerInfo]
    par: dict[str, float]
    starting: dict[str, StartingPosition]
    my_team: str
    sales: list[Sale] = field(default_factory=list)
    rostered_ids: set[str] = field(default_factory=set)
    """Players already under contract, so never on the auction board."""

    # -- recording ----------------------------------------------------------

    def record(self, player_id: str, team: str, price: int) -> Sale:
        if team not in self.starting:
            raise ValueError(f"unknown team {team!r}")
        if player_id in self.sold_ids:
            raise ValueError(f"{self.name_of(player_id)} has already been sold")
        if price < self.rules.min_bid:
            raise ValueError(f"price ${price} is below the ${self.rules.min_bid} minimum bid")

        info = self.players.get(player_id) or PlayerInfo(player_id=player_id, name=player_id)
        sale = Sale(
            sequence=len(self.sales),
            player_id=player_id,
            player_name=info.name,
            team=team,
            price=price,
            position=info.position,
        )
        self.sales.append(sale)
        return sale

    def undo(self) -> Sale | None:
        """Reverse the most recent sale. Mistyped prices are the common case."""
        return self.sales.pop() if self.sales else None

    # -- derived state ------------------------------------------------------

    @property
    def sold_ids(self) -> set[str]:
        return {sale.player_id for sale in self.sales}

    def name_of(self, player_id: str) -> str:
        info = self.players.get(player_id)
        return info.name if info else player_id

    def available(self) -> list[PlayerInfo]:
        sold = self.sold_ids
        return [
            info for pid, info in self.players.items()
            if pid not in sold and pid not in self.rostered_ids
        ]

    def status(self, team: str) -> TeamStatus:
        start = self.starting[team]
        spent = sum(sale.price for sale in self.sales if sale.team == team)
        won = sum(1 for sale in self.sales if sale.team == team)
        budget = self.rules.salary_cap - start.committed_salary - spent
        slots = max(0, self.rules.max_roster - start.roster_count - won)
        return TeamStatus(
            team=team,
            budget=budget,
            filled=start.roster_count + won,
            slots_to_fill=slots,
            max_bid=max_affordable_bid(budget, slots, self.rules.min_bid),
            spent=spent,
            is_me=team == self.my_team,
        )

    def all_status(self) -> list[TeamStatus]:
        return sorted(
            (self.status(team) for team in self.starting),
            key=lambda s: s.max_bid,
            reverse=True,
        )

    # -- economics ----------------------------------------------------------

    def remaining_dollars(self) -> int:
        return sum(self.status(team).budget for team in self.starting)

    def remaining_slots(self) -> int:
        return sum(self.status(team).slots_to_fill for team in self.starting)

    def inflation(self) -> float:
        """Ratio of money left to par value left, above the minimum-bid floor.

        Above 1.0 the room has money to burn and everything still on the board
        will go over par; below 1.0 the money went early and there are bargains
        coming. Measured on discretionary dollars only -- the $1 per slot every
        owner must reserve is not available to bid up anyone, so including it
        would damp the signal toward 1.0 and hide exactly what this is for.
        """
        slots = self.remaining_slots()
        if slots <= 0:
            return 1.0

        discretionary = self.remaining_dollars() - slots * self.rules.min_bid
        board = sorted(self.available(), key=lambda p: self.par.get(p.player_id, 0.0), reverse=True)
        par_left = sum(
            max(0.0, self.par.get(p.player_id, 0.0) - self.rules.min_bid)
            for p in board[:slots]
        )
        if par_left <= 0:
            return 1.0
        return max(0.0, discretionary / par_left)

    def adjusted_price(self, player_id: str) -> float:
        par = self.par.get(player_id, float(self.rules.min_bid))
        return self.rules.min_bid + max(0.0, par - self.rules.min_bid) * self.inflation()

    # -- advice -------------------------------------------------------------

    def bid_advice(self, player_id: str) -> BidAdvice:
        info = self.players.get(player_id) or PlayerInfo(player_id=player_id, name=player_id)
        adjusted = self.adjusted_price(player_id)
        mine = self.status(self.my_team)

        contenders = tuple(
            (status.team, status.max_bid)
            for status in self.all_status()
            if not status.is_me and status.can_bid and status.max_bid > adjusted
        )

        own_par = self.par.get(player_id, float(self.rules.min_bid))
        beneath = [
            p for p in self.available()
            if p.player_id != player_id
            and p.position == info.position
            and self.par.get(p.player_id, 0.0) <= own_par
        ]
        beneath.sort(key=lambda p: self.par.get(p.player_id, 0.0), reverse=True)
        next_best = beneath[0] if beneath else None
        gap = adjusted - self.adjusted_price(next_best.player_id) if next_best else adjusted

        return BidAdvice(
            player=info,
            par=self.par.get(player_id, float(self.rules.min_bid)),
            adjusted=adjusted,
            my_max_bid=mine.max_bid,
            walk_away=min(mine.max_bid, round(adjusted)),
            contenders=contenders,
            next_best=next_best,
            next_best_gap=gap,
        )

    def board(self, limit: int = 40) -> list[BidAdvice]:
        """Everything still available, dearest first."""
        ranked = sorted(
            self.available(), key=lambda p: self.par.get(p.player_id, 0.0), reverse=True
        )
        return [self.bid_advice(p.player_id) for p in ranked[:limit]]

    def nomination_candidates(self, limit: int = 8, protect: int = 12) -> list[BidAdvice]:
        """Who to put up: expensive players you are not trying to win.

        Nominating someone you want invites the room to bid against you while
        everyone still has money. Nominating someone you do not want drains
        their budgets instead, and the players you actually want get cheaper
        every time a rival spends. `protect` is how many of the top remaining
        players to treat as yours and keep off the block.
        """
        ranked = sorted(
            self.available(), key=lambda p: self.par.get(p.player_id, 0.0), reverse=True
        )
        return [self.bid_advice(p.player_id) for p in ranked[protect : protect + limit]]

    # -- construction -------------------------------------------------------

    @classmethod
    def start(
        cls,
        rules: ContractRules,
        players: dict[str, PlayerInfo],
        par: dict[str, float],
        starting: list[StartingPosition],
        my_team: str,
        rostered_ids: set[str] | None = None,
    ) -> "LiveAuction":
        return cls(
            rules=rules,
            players=players,
            par=par,
            starting={s.team: s for s in starting},
            my_team=my_team,
            rostered_ids=set(rostered_ids or ()),
        )

    def replay(self, sales: list[Sale]) -> None:
        """Restore from a persisted sale log, in order."""
        ordered = sorted(sales, key=lambda sale: sale.sequence)
        self.sales = [replace(sale, sequence=i) for i, sale in enumerate(ordered)]
