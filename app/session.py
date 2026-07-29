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
from data.models import Contract, ContractRules, LeagueSettings, Player
from engine.auction import AuctionMarket, max_affordable_bid
from engine.cuts import LeagueEquilibrium, RetentionPolicy, TeamRoster, solve_equilibrium
from engine.live_auction import LiveAuction, PlayerInfo, StartingPosition, par_prices
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
    player_info: dict[str, PlayerInfo]
    all_players: tuple[Player, ...]
    my_team: str
    season: int
    published_total: float

    policy: RetentionPolicy = RetentionPolicy.SURPLUS_MAXIMIZING
    cut: set[str] = field(default_factory=set)
    """player_ids the owner has chosen to release."""
    tagged: set[str] = field(default_factory=set)
    tags_available: int = 1
    post_deadline_source: str | None = None
    """Set once the real post-deadline rosters have been imported."""

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
            player_info={
                p.player_id: PlayerInfo(p.player_id, p.name, p.position, p.nfl_team)
                for p in players
                if p.player_id in universe
            },
            all_players=tuple(players),
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

    # -- post-deadline import -----------------------------------------------

    def adopt_post_deadline_rosters(self, roster_path: Path) -> list[str]:
        """Replace projected rosters with the real ones, and report any violations.

        Until 17 August every rival's post-cut roster is the optimizer's guess.
        After it they are simply known, and a guess is strictly worse than a
        fact -- the auction's opening budgets are the single input every other
        figure depends on, so drafting off projections when the real thing
        exists would put a modelling error under every price on the board.

        Your own cut/keep decisions are cleared, not merged: the new workbook
        already reflects whatever you actually dropped, so re-applying them
        would double-count.

        Returns a list of compliance problems rather than raising. A team over
        the cap after the deadline means the workbook is stale or the
        commissioner has not finished processing drops -- worth surfacing
        loudly, but not worth refusing to open the auction over.
        """
        imports = load_roster_workbook(roster_path)
        rosters = tuple(
            TeamRoster(
                name=team.team,
                contracts=tuple(_apply_protection(c, self.season) for c in team.contracts),
            )
            for team in imports
        )
        if not any(r.name == self.my_team for r in rosters):
            names = ", ".join(r.name for r in rosters)
            raise ValueError(
                f"no team named {self.my_team!r} in {roster_path}; found: {names}"
            )

        contracts = [c for r in rosters for c in r.contracts]
        links, unmatched = link_contracts_to_players(contracts, list(self.all_players))

        self.rosters = rosters
        self.links = links
        self.unmatched = tuple(unmatched)
        self.cut.clear()
        self.tagged.clear()
        self._cache.clear()
        self.post_deadline_source = str(roster_path)
        return self.compliance_issues()

    def compliance_issues(self) -> list[str]:
        """Teams that are over the cap or over the roster limit, in plain words."""
        issues = []
        for roster in self.rosters:
            if roster.salary > self.rules.salary_cap:
                issues.append(
                    f"{roster.name} is ${roster.salary - self.rules.salary_cap} over the cap"
                )
            if len(roster.contracts) > self.rules.max_roster:
                issues.append(
                    f"{roster.name} has {len(roster.contracts)} players, "
                    f"over the {self.rules.max_roster} limit"
                )
        return issues

    # -- live auction -------------------------------------------------------

    def start_auction(self) -> LiveAuction:
        """Open the auction from the post-drop-deadline state.

        Your own starting position comes from the keep/cut decisions you made
        on the board; every rival's comes from the optimizer's projection for
        them under the active scenario. On 24 August those projections should
        be replaced by re-importing the actual post-deadline workbook -- the
        drop deadline is a week earlier, so the real rosters will be known.

        Par prices are re-cleared over the auction's own board rather than
        reused from the league equilibrium, so inflation opens at 1.0 and every
        later reading measures the room rather than a normalization artefact.
        """
        equilibrium = None if self.post_deadline_source else self.equilibrium()

        starting: list[StartingPosition] = []
        kept_ids: set[str] = set()
        for roster in self.rosters:
            if self.post_deadline_source:
                keep = roster.contracts  # the deadline has passed; these are facts
            elif roster.name == self.my_team:
                keep = self.kept_contracts()
            else:
                keep = equilibrium.plan(roster.name).keep
            kept_ids.update(self.key(c) for c in keep)
            starting.append(
                StartingPosition(
                    team=roster.name,
                    committed_salary=sum(c.salary for c in keep),
                    roster_count=len(keep),
                )
            )

        dollars = sum(self.rules.salary_cap - s.committed_salary for s in starting)
        slots = sum(max(0, self.rules.max_roster - s.roster_count) for s in starting)
        board = [pv for pid, pv in self.universe.items() if pid not in kept_ids]

        return LiveAuction.start(
            rules=self.rules,
            players={
                pid: info for pid, info in self.player_info.items() if pid not in kept_ids
            },
            par=par_prices(board, dollars, slots, self.rules.min_bid),
            starting=starting,
            my_team=self.my_team,
            rostered_ids=kept_ids,
        )

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

