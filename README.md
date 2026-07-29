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

**FFL-NY auction** — Phases 1–3 complete: the contract lifecycle,
market-clearing auction pricing, joint cut/keep/franchise-tag optimization,
steal-round math, multi-year contract valuation, and a desktop app covering
both the 17 Aug drop deadline and the 24 Aug live auction. The auction work is
additive — snake-specific modules are untouched.

### Desktop app

```bash
uv run python -m app.desktop path/to/rosters.xlsx path/to/etr_auction_values.csv
```

Opens a native window (pywebview over a loopback FastAPI server) with two
screens:

- **Cut / keep** — your roster priced at equilibrium, the optimizer's
  keep/cut/tag recommendation, both scenario brackets, and the league-wide cap
  position.
- **Live auction** (`/auction`) — keyboard-driven bid entry, live budgets and
  max bids for all 12 teams, inflation-adjusted prices, walk-away numbers, and
  a nomination queue. Sales persist to SQLite as they are entered; `u` undoes.

Add `--no-window` to serve without a GUI toolkit. No network, no build step, no
CDN — it has to work in somebody's living room on draft night.

Rehearse the auction end to end before the day:

```bash
uv run python scripts/mock_auction.py path/to/rosters.xlsx path/to/etr_auction_values.csv
```

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
