"""Loaded league state and the decisions being made against it.

Holds one session's worth of everything the cut/keep screen needs: the league
rules, all twelve rosters, the player universe, and the owner's own keep/cut
and tag choices.

The important wrinkle is that your decisions move the market. Releasing a
contract puts its salary back in your budget *and* puts the player into the
auction pool, which changes what everything costs -- including the contracts
you are still deciding on. So the equilibrium is re-solved with your current
keep set pinned as an override, rather than letting the solver re-optimize
your roster back to whatever it thinks is best.

Solves are cached on the decisions that determine them, because a fixed-point
solve across twelve teams is far too slow to run on every checkbox click.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from config.settings import load_league_settings
from data.contracts import franchise_tag_salary
from data.ingest_etr import load_etr_auction_values
from data.ingest_roster import (
    contract_player_id,
    link_contracts_to_players,
    load_roster_workbook,
)
from data.models import Contract, ContractRules, LeagueSettings
from engine.auction import AuctionMarket, max_affordable_bid
from engine.cuts import LeagueEquilibrium, RetentionPolicy, TeamRoster, solve_equilibrium
from engine.replacement import PlayerValue, positions_with_demand
from engine.roster_plan import RosterPlan, plan_roster

# 2025 rookie protections held all year (7.3), so exempt from escalation and
# from steal attempts through 2026. The roster workbook cannot know these --
# they live in the league's rules sheet.
ROOKIE_PROTECTED_THROUGH_2026 = {
    "Travis Hunter", "Emeka Egbuka", "Tyler Warren", "Bhayshul Tuten",
}


@dataclass
class Session:
    league: LeagueSettings
    rosters: tuple[TeamRoster, ...]
    universe: dict[str, PlayerValue]
    links: dict[str, str]
    unmatched: tuple[Contract, ...]
    my_team: str
    season: int
    published_total: float

    policy: RetentionPolicy = RetentionPolicy.SURPLUS_MAXIMIZING
    cut: set[str] = field(default_factory=set)
    """player_ids the owner has chosen to release."""
    tagged: set[str] = field(default_factory=set)
    tags_available: int = 1

    _cache: dict = field(default_factory=dict, repr=False)

    # -- loading ------------------------------------------------------------

    @classmethod
    def load(
        cls,
        league_path: Path,
        roster_path: Path,
        etr_path: Path,
        *,
        my_team: str = "Andrew's Team",
        season: int = 2026,
        value_column: str = "half_ppr",
    ) -> "Session":
        league = load_league_settings(league_path)
        if league.contract_rules is None:
            raise ValueError(f"{league_path} has no `contracts:` block; not an auction league")

        players, published = load_etr_auction_values(etr_path, value_column)
        startable = positions_with_demand(league)
        by_id = {p.player_id: p for p in players}

        from engine.auction import implied_vorp

        universe = {
            pid: PlayerValue(player_id=pid, position=by_id[pid].position, value=value)
            for pid, value in implied_vorp(published, league.contract_rules.min_bid).items()
            if by_id[pid].position in startable
        }

        imports = load_roster_workbook(roster_path)
        rosters = tuple(
            TeamRoster(
                name=team.team,
                contracts=tuple(_apply_protection(c, season) for c in team.contracts),
            )
            for team in imports
        )
        contracts = [c for r in rosters for c in r.contracts]
        links, unmatched = link_contracts_to_players(contracts, players)

        if not any(r.name == my_team for r in rosters):
            names = ", ".join(r.name for r in rosters)
            raise ValueError(f"no team named {my_team!r} in {roster_path}; found: {names}")

        return cls(
            league=league,
            rosters=rosters,
            universe=universe,
            links=links,
            unmatched=tuple(unmatched),
            my_team=my_team,
            season=season,
            published_total=sum(published.values()),
        )

    # -- basics -------------------------------------------------------------

    @property
    def rules(self) -> ContractRules:
        assert self.league.contract_rules is not None
        return self.league.contract_rules

    def key(self, contract: Contract) -> str:
        raw = contract_player_id(contract)
        return self.links.get(raw, raw)

    @property
    def my_roster(self) -> TeamRoster:
        return next(r for r in self.rosters if r.name == self.my_team)

    def effective_contracts(self) -> tuple[Contract, ...]:
        """My roster with any franchise tags applied, as the market should see it."""
        return tuple(
            replace(c, salary=franchise_tag_salary(c.salary, self.rules),
                    franchise_tagged_season=self.season)
            if self.key(c) in self.tagged else c
            for c in self.my_roster.contracts
        )

    def kept_contracts(self) -> tuple[Contract, ...]:
        return tuple(c for c in self.effective_contracts() if self.key(c) not in self.cut)

    # -- solving ------------------------------------------------------------

    def _cache_key(self) -> tuple:
        return (self.policy, frozenset(self.cut), frozenset(self.tagged), self.tags_available)

    def equilibrium(self) -> LeagueEquilibrium:
        """Market solved with my current keep set pinned, so my choices move prices."""
        cache_key = ("eq", *self._cache_key())
        if cache_key not in self._cache:
            self._cache[cache_key] = solve_equilibrium(
                self.rosters, self.universe, self.rules, self.league.num_teams,
                key=self.key, policy=self.policy,
                overrides={self.my_team: self.kept_contracts()},
            )
        return self._cache[cache_key]

    @property
    def market(self) -> AuctionMarket:
        return self.equilibrium().market

    def recommendation(self) -> RosterPlan:
        """The optimizer's own answer, priced under the current scenario.

        Solved against a market where my roster is optimized rather than
        pinned -- otherwise the recommendation would be conditioned on the
        decisions it is supposed to be advising about.
        """
        cache_key = ("rec", self.policy, self.tags_available)
        if cache_key not in self._cache:
            free = solve_equilibrium(
                self.rosters, self.universe, self.rules, self.league.num_teams,
                key=self.key, policy=self.policy,
            )
            self._cache[cache_key] = plan_roster(
                self.my_roster.contracts,
                lambda c: free.market.price(self.key(c)),
                self.rules, self.season, tags_available=self.tags_available,
            )
        return self._cache[cache_key]

    # -- views --------------------------------------------------------------

    def my_rows(self) -> list[dict]:
        market = self.market
        recommended = {self.key(c) for c in self.recommendation().keep}
        recommended_tags = {self.key(t.contract) for t in self.recommendation().tags}

        rows = []
        for original, effective in zip(self.my_roster.contracts, self.effective_contracts()):
            pid = self.key(original)
            price = market.price(pid)
            rows.append(
                {
                    "id": pid,
                    "name": original.player_name,
                    "position": original.position.value if original.position else "",
                    "nfl_team": original.nfl_team or "",
                    "salary": effective.salary,
                    "base_salary": original.salary,
                    "market": price,
                    "surplus": price - effective.salary,
                    "kept": pid not in self.cut,
                    "tagged": pid in self.tagged,
                    "protected": original.is_rookie_protected(self.season),
                    "recommended_keep": pid in recommended,
                    "recommended_tag": pid in recommended_tags,
                }
            )
        return sorted(rows, key=lambda r: r["surplus"], reverse=True)

    def summary(self) -> dict:
        kept = self.kept_contracts()
        salary = sum(c.salary for c in kept)
        budget = self.rules.salary_cap - salary
        slots = max(0, self.rules.max_roster - len(kept))
        market = self.market
        return {
            "kept": len(kept),
            "salary": salary,
            "budget": budget,
            "slots": slots,
            "max_bid": max_affordable_bid(budget, slots, self.rules.min_bid),
            "over_cap": salary > self.rules.salary_cap,
            "cap": self.rules.salary_cap,
            "surplus": sum(market.price(self.key(c)) - c.salary for c in kept),
            "auction_dollars": market.dollars,
            "auction_slots": market.slots,
            # None rather than a negative percentage: a roster still over the
            # cap has no share of the auction to speak of, and rendering "-3%"
            # invites reading it as a small share instead of an illegal roster.
            "share": _share(budget, market.dollars),
            "tags_used": len(self.tagged),
            "tags_available": self.tags_available,
        }

    def league_table(self) -> list[dict]:
        equilibrium = self.equilibrium()
        rows = []
        for roster in self.rosters:
            plan = equilibrium.plan(roster.name)
            rows.append(
                {
                    "team": roster.name,
                    "committed": roster.salary,
                    "players": len(roster.contracts),
                    "must_cut": max(0, roster.salary - self.rules.salary_cap),
                    "projected_keep": len(plan.keep),
                    "projected_budget": plan.bid_budget(self.rules),
                    "is_mine": roster.name == self.my_team,
                }
            )
        return sorted(rows, key=lambda r: r["must_cut"], reverse=True)

    def scenarios(self) -> list[dict]:
        """Both brackets, each showing what my budget would be worth in it."""
        out = []
        for policy in RetentionPolicy:
            cache_key = ("scen", policy, frozenset(self.cut), frozenset(self.tagged))
            if cache_key not in self._cache:
                self._cache[cache_key] = solve_equilibrium(
                    self.rosters, self.universe, self.rules, self.league.num_teams,
                    key=self.key, policy=policy,
                    overrides={self.my_team: self.kept_contracts()},
                )
            result = self._cache[cache_key]
            budget = self.rules.salary_cap - sum(c.salary for c in self.kept_contracts())
            out.append(
                {
                    "policy": policy.value,
                    "label": policy.value.replace("_", " "),
                    "dollars": result.market.dollars,
                    "slots": result.market.slots,
                    "per_slot": result.market.dollars / max(result.market.slots, 1),
                    "share": _share(budget, result.market.dollars),
                    "active": policy == self.policy,
                }
            )
        return out

    # -- mutations ----------------------------------------------------------

    def toggle_cut(self, player_id: str) -> None:
        self.cut.symmetric_difference_update({player_id})

    def toggle_tag(self, player_id: str) -> bool:
        """Apply or remove a tag. Returns False if no tag is available to spend."""
        if player_id in self.tagged:
            self.tagged.discard(player_id)
            return True
        if len(self.tagged) >= min(self.tags_available, self.rules.max_franchise_tags):
            return False
        self.tagged.add(player_id)
        self.cut.discard(player_id)  # tagging a player you are cutting makes no sense
        return True

    def apply_recommendation(self) -> None:
        plan = self.recommendation()
        keep = {self.key(c) for c in plan.keep}
        self.cut = {self.key(c) for c in self.my_roster.contracts if self.key(c) not in keep}
        self.tagged = {self.key(t.contract) for t in plan.tags}

    def reset(self) -> None:
        self.cut.clear()
        self.tagged.clear()


def _share(budget: int, dollars: int) -> float | None:
    """Fraction of the auction's money this budget represents, or None if there is none."""
    if budget <= 0 or dollars <= 0:
        return None
    return budget / dollars


def _apply_protection(contract: Contract, season: int) -> Contract:
    if contract.player_name in ROOKIE_PROTECTED_THROUGH_2026:
        return replace(contract, rookie_protected_through=season)
    return contract
