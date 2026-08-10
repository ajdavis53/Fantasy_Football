# Fantasy Football Snake Draft Optimizer

Draft-day recommendation tool for two snake draft leagues. See
`docs/PROJECT_NOTES.md` for the phase roadmap, the decision log, and the
open questions still waiting on the league owner.

## Commands

```bash
uv sync                                    # install
uv run pytest                              # full suite (fast, no network)
uv run streamlit run ui/app.py             # the draft assistant

uv run python scripts/build_board.py config/leagues/live_league.yaml <etr.xlsx>
uv run python scripts/mock_draft.py config/leagues/live_league.yaml <etr.xlsx> --slot 5
uv run python scripts/make_sample_rankings.py data/sample_rankings.xlsx   # demo data, not real rankings
```

## The two leagues

| | Live (in person) | Sleeper |
|---|---|---|
| Teams | 12 | 10 |
| Starters | QB, 2 RB, 2 WR, TE, 3 FLEX | same + DEF |
| Bench | 7 (16 rounds) | 8 (18 rounds) |
| Kicker | none | none |
| Keepers | yes, cost a specific round's pick | same |
| Picks entered | by hand, under a clock | Sleeper API (phase 3, not built) |

Both are full PPR. Configs live in `config/leagues/*.yaml`.

## Architecture

The engine is pure functions parameterized by a `LeagueSettings`. There is no
branching on *which* league anywhere in `engine/` — two YAML configs drive two
independent runs over the same player data. Keep it that way; it is what makes
a third league free.

- `data/models.py` — domain types (`Player`, `LeagueSettings`, `RosterSlots`, `Keeper`, ...)
- `data/ingest_etr.py` — parse the ETR export (.xlsx "Full Ledger" sheet, or .csv)
- `data/projections.py` — turn ranks into points (see below)
- `data/name_matching.py` — fuzzy name lookup, shared by keeper resolution and live entry
- `engine/replacement.py` — replacement baselines, FLEX allocation, rosterable filter
- `engine/vbd.py`, `engine/tiers.py`, `engine/scoring.py` — value, tiers, stat scoring
- `engine/draft_state.py` — pick schedule, snake math, pick history, autosave
- `engine/recommend.py` — ranked pick suggestions with reasons
- `ui/app.py` — Streamlit draft assistant
- `sim/` — empty; phase 4 (Monte Carlo) plugs in here

`engine/` has no network dependency and is fully testable offline. All I/O
lives in `data/` and `integrations/`.

## Things that will bite you

**The ETR export has no projected points and no tiers.** It ships rank,
positional rank, and ADP only. VBD is a *points* differential, so
`data/projections.py` fits points-by-positional-rank curves from recent
nflverse seasons under the league's own scoring rules and reads ETR's ranks
off them. Curves are smoothed deliberately: raw ex-post order statistics take
the luckiest season anyone had at each rank as if it were an expectation, and
uncorrected that rates the QB1 several rounds above where both ETR and the
market put him. If a real ETR projections export ever appears, its points take
precedence automatically via `PlayerRanking.projected_points`.

**Draft order is a materialized schedule, not a formula.** Keepers cost a
specific round's pick and teams keep different numbers, so the order has
per-team holes and pick number no longer implies a team. Everything reads from
`build_pick_schedule`. The pure snake helpers still exist and are still
correct for the keeperless case, which the schedule reproduces exactly.

**A position with no starter slot must be filtered out**, not merely
deprioritized. Left in, it gets a replacement baseline of zero and banks its
entire projection as value over replacement — kickers ranked ~15th overall in
a league that cannot start one. See `filter_to_rosterable`.

**Cross-position VORP stops being comparable late in a draft.** The deep
positions fall below replacement while shallow ones stay above their own
baseline, so raw VORP will happily recommend an eighth defense. `recommend`
guards this with a per-position capacity derived from the league-wide flex
allocation, plus overflow restricted to flex-eligible positions.

**`recommend` needs escalating urgency on unfilled starters.** A flat need
boost is not enough: a low-VORP but required position never wins a round, and
a greedy drafter reaches the final round with no quarterback and an illegal
lineup.

**Name matching uses `token_set_ratio`, not `WRatio`.** Shared surnames are
everywhere; WRatio's partial-substring bonus scores "amon ra st brown" against
"AJ Brown" at 86 and makes an obvious match look ambiguous. Genuinely
ambiguous input still refuses to auto-commit — recording the wrong player
mid-draft is worse than asking.

**nflverse may not have published the most recent season.** Seasons are
fetched individually and a missing one degrades to a warning.

## Testing

`uv run pytest` — 109 tests, all offline and fast. Unit tests use synthetic
boards; `tests/conftest.py` holds the 4-team fixture league.

Unit tests are not sufficient here. Every roster-construction bug so far was
found by `scripts/mock_draft.py` running a full draft, not by the suite. Run a
mock after any change to `engine/recommend.py`; it exits non-zero if the
resulting roster cannot field a legal lineup.

For UI changes, drive the real thing with Playwright (`/opt/pw-browsers/chromium`)
rather than trusting that it renders.
