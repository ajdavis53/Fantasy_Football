# Fantasy Football Draft Tools

Draft-day recommendation tools for three leagues, sharing one valuation engine
(projections + value-based drafting + tiering), parameterized per-league by
scoring rules and roster construction. See `config/leagues/` for per-league
settings.

**Snake draft leagues:**

- A live, in-person league (picks entered manually during the draft).
- A Sleeper league (picks synced automatically via Sleeper's API).

**Dynasty auction league:**

- FFL-NY ("HARD STUFF"), a 12-team $300-cap dynasty auction with salary
  escalation, franchise tags, rookie protection, and a steal round. See
  [`docs/ffl-ny/PLAN.md`](docs/ffl-ny/PLAN.md) for the build plan and
  [`docs/ffl-ny/league-rules.md`](docs/ffl-ny/league-rules.md) for the rules
  the app models.

## Status

**Snake leagues** — Phase 0/1: data foundation and the VBD/tiering engine.
Roadmap: data ingestion -> engine -> live manual draft UI -> Sleeper sync ->
Monte Carlo opponent simulation -> optimizer stretch goal.

**FFL-NY auction** — Phase 1 complete: contract lifecycle, market-clearing
auction pricing, cut/keep optimization, steal-round math, and multi-year
contract valuation, all headless and tested. Next up is the cut/keep UI
(Phase 2) and the live auction assistant (Phase 3). The auction work is
additive — snake-specific modules are untouched.

### Auction values are re-solved, not rescaled

Published auction values (ETR's) are an allocation of a *from-scratch* draft:
their Half PPR column sums to exactly $2,400, being 12 teams × $200. A keeper
league breaks that — most of the money is committed to contracts and most of
the players are owned — so rescaling by a cap ratio is the wrong
transformation, not merely an imprecise one. `engine/auction.py` inverts
published values back to value-over-replacement and re-clears them against the
dollars and slots the auction will actually have; `engine/cuts.py` closes the
loop, since those dollars depend on what every owner cuts and what they cut
depends on prices.

### Offseason report

```bash
uv run python scripts/ffl_ny_report.py path/to/rosters.xlsx path/to/etr_auction_values.csv
```

Runs the whole pipeline on the real files and prints the league cap position,
both scenario brackets, your roster priced at equilibrium, and ranked steal
targets. See [`docs/ffl-ny/2026-offseason-decisions.md`](docs/ffl-ny/2026-offseason-decisions.md)
for the analysis it produced.

## Setup

```bash
uv sync
uv run pytest
```

## Player rankings input

Rankings come from a user-supplied Establish The Run (ETR) export — either
their `.xlsx` cheat sheet or a `.csv` — ingested via `data/ingest_etr.py`.
For workbooks the default sheet is ETR's **Full Ledger** tab, which carries
ADP; the Cheat Sheet tab is a printable layout of the same players with no
extra data. Column matching is alias-based, so a renamed column can be
handled with an override rather than a code change.

ETR's Top-300 export has **no projected points and no tiers**, so:

- `data/projections.py` fits points-by-positional-rank curves from recent
  seasons under *this league's own scoring rules*, then reads ETR's ranks off
  those curves. ETR supplies the opinion (who is better), history supplies the
  shape (how much better). If an ETR projections export is ever available, its
  points take precedence automatically.
- Tiers fall back to gap detection in `engine/tiers.py`.

## Building a board

```bash
uv run python scripts/build_board.py config/leagues/sleeper_league.yaml path/to/etr.xlsx
```

The `EDGE` column is ADP minus ETR rank: positive means ETR rates a player
above where the market drafts him (value), negative means the market reaches.
