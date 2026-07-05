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

Player rankings/tiers come from a user-supplied Establish The Run (ETR) CSV
export, ingested via `data/ingest_etr.py`. The exact column layout is
configurable in that module since ETR's export schema may change.
