# Fantasy Football Snake Draft Optimizer

A draft-day recommendation tool for two snake draft leagues:

- A live, in-person league (picks entered manually during the draft).
- A Sleeper league (picks synced automatically via Sleeper's API).

Both leagues share one recommendation engine (value-based drafting + tiering),
parameterized per-league by scoring rules and roster construction. See
`config/leagues/` for per-league settings.

## Status

Phase 0/1: data foundation and the VBD/tiering engine. See the project plan
for the full phased roadmap (data ingestion -> engine -> live manual draft UI
-> Sleeper sync -> Monte Carlo opponent simulation -> optimizer stretch goal).

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
