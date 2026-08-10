# Project notes

Roadmap, decisions and open questions. `CLAUDE.md` covers how to work in the
codebase; this file covers why it looks the way it does and what is left.

## Where things stand

| Phase | Status |
|---|---|
| 0 — Data foundation | done |
| 1 — VBD + tiering engine | done |
| 2 — Live manual draft assistant | **done, usable** |
| 3 — Sleeper live sync | not started |
| 4 — Monte Carlo opponent simulation (real VONA) | not started |
| 5 — Full-roster optimizer (MILP/MCTS) | stretch, may never be needed |

Both drafts are in late August. Phase 2 is the one the in-person league cannot
draft without, and it works today.

## Waiting on the league owner

1. **Keeper lists for both leagues.** Needed per keeper: which team (by draft
   slot), which player, and which round it costs. This is the whole league's
   keepers, not just ours — other teams' forfeited picks change when we are on
   the clock. `keepers: []` in both YAMLs, format documented inline.
2. **Sleeper `league_id`** (and `draft_id` once the draft exists). Readable
   from the league URL: `sleeper.com/leagues/<league_id>/...`. Sleeper username
   is `ajdavis53`; `GET /v1/user/ajdavis53` → user_id → leagues also works.
3. **Draft slots**, once known. Not blocking — settable in the UI sidebar.

## Decisions, and why

**Rankings come from an ETR export, not a scraper.** ETR is a paid
subscription and its articles are paywalled; the rankings export is used
because the owner exports it themselves. Do not add scraping of ETR content.

**Points are derived, not sourced.** The Top-300 export carries no
projections, so points come from historical positional-value curves fitted
under each league's own scoring. This keeps ETR as the opinion (who is better)
and history as the shape (how much better). It also means scoring rules stay
genuinely configurable, which was an explicit requirement for future leagues.

**Tiers are computed, not sourced.** The export has no tier column — verified
including the cheat-sheet cell fills, which encode position, not tier. So
`engine/tiers.py` gap-detection is the live path; `tiers_from_rankings` is
kept for the day a source does supply them.

**ADP is used as a market signal.** The export includes ADP, which closed a
gap the original plan had flagged as unsolved. `EDGE` (ADP − rank) surfaces
where ETR disagrees with the market, which partially automates the
"late-round targets vs. players to avoid" judgement the owner previously got
from reading ETR's articles.

**Recommendations are heuristic and explainable, on purpose.** Under a pick
clock a single score is useless; each row carries short reasons. Real opponent
simulation is phase 4 — the current "unlikely to last to your next pick" flag
is a deterministic worst-case stand-in, and it is suppressed when it would
apply to every row, since a warning on everything is noise.

**QB valuation resolved itself.** Early boards rated elite QBs several rounds
above both ETR and ADP. Curve smoothing fixed part of it; three flex spots
fixed the rest, by creating enough RB/WR demand to suppress QB value
naturally. No manual thumb on the scale was needed.

## Known limitations

- **Rosters skew WR-heavy** (about 8 WR / 4 RB / 2 TE / 2 QB in the live
  league). Defensible in 3-flex full PPR, but it is the engine's opinion. The
  weights in `engine/recommend.py` are the tuning surface; run mocks to judge.
- **Traded or out-of-order picks are not reconciled.** `record_pick` accepts an
  explicit `team_index`, but the schedule does not shift, so turn predictions
  assume the configured order.
- **K/DEF curves are synthetic.** nflverse seasonal data is offence-only.
  Irrelevant to the live league, and near-irrelevant to Sleeper where one DEF
  starts and VBD lands near zero regardless.
- **Curves fit on 3 seasons**, since nflverse had not published the most recent
  one at time of writing. It will be picked up automatically.

## Phase 3 notes (Sleeper sync), before starting

The risky part is **not** polling `GET /v1/draft/<draft_id>/picks` — that is a
simple JSON GET. It is the **ID crosswalk**: Sleeper identifies players by its
own IDs across roughly 11k records, and mismatching one means the tool marks
the wrong player as drafted mid-draft, which is worse than no sync at all.

Plan: build the crosswalk from `nfl_data_py.import_ids()` (it carries
`sleeper_id` and `gsis_id`), fall back to fuzzy name+team+position via
`data/name_matching.py`, log unmatched loudly, and keep a manual override file.
Validate against a real Sleeper mock draft before trusting it live.

Sleeper's `/v1/players/nfl` also carries `injury_status`, `injury_body_part`
and `news_updated`, which is most of the player-news feature discussed —
structured, official, no scraping. Pre-fetch and cache it before the draft
rather than fetching during a pick; a hanging request on the clock is the
worst possible failure. RSS feeds (PFF, Razzball, RotoBaller) would add camp
narrative later.

Note `api.sleeper.app` is blocked by the egress policy on Claude Code for web.
Locally, allow it via `sandbox.network.allowedDomains`.
