# FFL-NY Dynasty Auction Assistant — Build Plan

A desktop app for the FFL-NY ("HARD STUFF") 12-team dynasty auction league,
built for a team taken over mid-stream in an established league.

Companion documents:
- [`league-rules.md`](./league-rules.md) — condensed operative rules
- [`../../data/leagues/ffl_ny/2026_preseason_rosters.csv`](../../data/leagues/ffl_ny/2026_preseason_rosters.csv) — all 12 rosters with salaries, parsed from the preseason workbook

---

## 1. The situation

### 1.1 The calendar is the binding constraint

| Event | Date | Days from 7/28 |
|---|---|---|
| **Steal Round** | Mon **8/3/26**, 9am–5pm | **6** |
| **Drop, Tag & Trade Deadline** | Mon **8/17/26**, midnight | 20 |
| **Auction Draft** | Mon **8/24/26**, 8–11pm (in person) | 27 |
| First Waivers | Wed 9/2/26 | 36 |
| Season starts | Wed 9/9/26 | 43 |

Three irreversible decisions land in 27 days, each gated on the one before it.
Trading freezes at the drop deadline and stays frozen through the auction, so
the 8/17 cut list is final and unhedgeable.

**The 8/3 steal round will be handled as a one-off written analysis, not
tooling** — six days is not enough to build something trustworthy, and the
throwaway scripts feed directly into the Phase 1 engine anyway.

### 1.2 The league is $498 over the cap, in aggregate

| | |
|---|---|
| Total committed salary | **$4,098** |
| Total cap (12 × $300) | **$3,600** |
| Teams over the cap | **9 of 12** |
| Players rostered | 170 (of 168 max roster spots) |

Every one of those nine teams must dump salary by 8/17. That forced selling is
the single biggest driver of auction prices this year, and it is knowable in
advance — which is exactly the edge the app should capture.

| Team | Owner | N | Salary | Must cut ≥ |
|---|---|---:|---:|---:|
| Tire Fire Sale | RJ Kalb | 15 | 380 | 80 |
| Canal Cats | Ben Adams | 14 | 370 | 70 |
| Joseph the Tank Engine | Joe Robison | 15 | 370 | 70 |
| Muff's Punters | Dan Muffoletto | 14 | 370 | 70 |
| **Andrew's Team** | **Andrew Davis** | **14** | **366** | **66** |
| Danheiser Dunces | Eric Danheiser | 14 | 363 | 63 |
| Pink Pony Club | Greg Semrau | 14 | 363 | 63 |
| The MidDermott's | John Hoertz | 15 | 351 | 51 |
| Houle's Heros | Jesse | 15 | 330 | 30 |
| Team X-Blades | Joe Lawless | 14 | 293 | — |
| Slobberknocker | Bob Willis | 12 | 283 | — |
| Lyon in Last | Jeremy Lyon | 14 | 259 | — |

### 1.3 Scaling ETR by 1.5× is the wrong transformation

The ETR Half PPR column sums to **exactly $2,400** — 12 teams × $200. It is a
market-clearing allocation: every dollar of a from-scratch auction distributed
across the full draftable pool.

FFL-NY is not a from-scratch auction. Multiplying by 1.5 to reach a $300 cap
produces a $3,600 allocation over all 459 players, but in FFL-NY:

- **Most of the money is already spent.** Auction dollars are only
  `$3,600 − (salaries retained after cuts)`.
- **Most of the players are unavailable.** The auction pool is only the players
  cut before 8/17 plus those nobody rostered.
- **Both quantities are decided by twelve owners in the same three weeks**, and
  they move together.

Applying 1.5× to the current rosters produces a league-wide surplus of
**−$680**, which is arithmetically impossible in a closed market — proof the
scalar is wrong rather than merely imprecise.

The correct transformation is a **re-solve**, not a multiplier: take ETR's
opinion of *who is better and by how much*, and re-clear the market against
this league's actual remaining dollars, remaining roster slots, and remaining
player pool. That engine is §3.2 and it is the heart of the app.

### 1.4 Andrew's Team is the second-most underwater roster in the league

Using raw ETR Half PPR purely as a sanity check (not as final valuation — §1.3),
the roster carries **$366 of salary against roughly $216 of redraft value**:

| Player | Pos | Salary | ETR ($200 scale) |
|---|---|---:|---:|
| Saquon Barkley | RB | 86 | 50 |
| Davante Adams | WR | 61 | 24 |
| A.J. Brown | WR | 55 | 36 |
| Jauan Jennings | WR | 26 | 0 |
| Jameson Williams | WR | 18 | 21 |
| Dak Prescott | QB | 17 | 8 |
| AJ Barner | TE | 16 | 0 |
| Isaiah Likely | TE | 16 | 0 |
| Dalton Schultz | TE | 16 | 0 |
| Kareem Hunt | RB | 15 | — (FA) |
| Dallas Goedert | TE | 14 | 1 |
| Devin Singletary | RB | 10 | 0 |
| Chris Godwin | WR | 8 | 3 |
| Dallas Cowboys | DEF | 8 | 1 |

Two structural problems are visible without any modeling: **$62 tied up in four
tight ends** when the lineup starts one, and **three running backs, none of them
cheap**, against a 2 RB + 2 FLEX requirement. Jameson Williams is the only
player on the roster who is plausibly underpaid.

A caveat the engine must handle: an ETR value of $0 means "outside the top ~111
valued players," not "worthless." With 168 roster spots in this league,
replacement level sits far deeper than ETR's redraft pricing implies, so those
zeros should resolve to roughly $1–3, not zero. That correction matters — it is
the difference between "cut everyone" and a real cut list.

---

## 2. Technology

Decisions taken (per your answers):

| Layer | Choice | Why |
|---|---|---|
| Engine | **Python 3.11+** | The existing repo's engine, tests, and ETR ingestion are already here and directly reusable. |
| UI | **FastAPI + HTMX**, server-rendered | One language, no build step, sub-100ms interactions. Streamlit re-runs the whole script per interaction — unusable at an auction where a bid needs entering in under two seconds. |
| Shell | **pywebview** | Wraps the local server in a native window; ships as a real `.app`/`.exe` via PyInstaller. Cross-platform, no Node toolchain. |
| State | **SQLite** | The auction needs undo, an audit trail, and crash recovery. The existing JSON-to-disk approach is too coarse for that. |
| Data in | **MFL CSV export + file import** | You have web login but no API, so ingestion is import-driven with a drag-and-drop path for MFL exports and the ETR sheet. |

**Offline by default.** The draft is in person, in someone's house, at 8pm. The
app must assume no network: everything is computed locally, and nothing blocks
on a fetch.

### 2.1 Reused from the existing repo

The repo currently holds a snake-draft optimizer for two other leagues. Its
foundation is league-agnostic and carries over:

| Module | Reuse |
|---|---|
| `data/models.py` | `Player`, `Position`, `ScoringRules`, `RosterSlot(s)`, `LeagueSettings` — extend with `Contract` |
| `data/ingest_etr.py` | ETR `.csv`/`.xlsx` ingestion, alias-based columns — add auction-value column aliases |
| `data/projections.py` | Fits points-by-positional-rank curves under a league's own scoring; ETR ships ranks, not points, so this is required |
| `data/name_matching.py` | Fuzzy matching — now doing triple duty across MFL, ETR, and the roster workbook |
| `engine/replacement.py` | Replacement baselines generalized over arbitrary roster construction, incl. multi-FLEX |
| `engine/vbd.py`, `engine/tiers.py` | VORP/VOLS and gap-based tiering — VORP is the input to auction pricing |

Snake-specific modules (`engine/draft_state.py`, `engine/recommend.py`,
`scripts/mock_draft.py`, `ui/app.py`) stay untouched and keep serving the other
two leagues. FFL-NY is added as a third league config plus new auction modules,
**not** as a rewrite.

### 2.2 New modules

```
config/leagues/ffl_ny.yaml      league settings: 0.5 PPR, 9 starters, no K, $300 cap, dynasty params
data/mfl.py                     MFL CSV export ingestion (rosters, salaries, transactions)
data/contracts.py               salary lifecycle: +$5/yr, franchise −$10, trade ×0.9, rookie protection
engine/auction.py               market-clearing auction pricing  ← core
engine/roster_optimizer.py      cut/keep/tag optimization under the cap
engine/steal.py                 steal-round attack and defense math
engine/live_auction.py          in-draft state, affordability, inflation
engine/dynasty.py               multi-year contract valuation
app/                            FastAPI + HTMX + pywebview desktop shell
```

---

## 3. The engine

### 3.1 Projections

ETR supplies ranks, not points. `data/projections.py` already fits
points-by-positional-rank curves from recent seasons under a given league's
scoring, then reads ETR's ranks off those curves — ETR supplies the opinion,
history supplies the scale. For FFL-NY that means refitting under **0.5 PPR**
with the league's DEF scoring, and **dropping kickers entirely** (no K slot, no
K scoring — `positions_with_demand` already handles this).

### 3.2 Market-clearing auction values — the core

Given a scenario (who cuts whom), compute:

1. `available` = players cut before 8/17 + players nobody rostered
2. `D` = total auction dollars = `Σ_teams (300 − retained_salary)`
3. `S` = total slots to fill = `Σ_teams (14 − retained_count)`
4. `VORP_i` = projected points − replacement level **at remaining demand**
   (replacement is deeper than a from-scratch draft because 170 players are
   already off the board)
5. Every filled slot costs at least $1, so discretionary money is `D − S`
6. ```
   price_i = 1 + (D − S) × VORP_i / Σ_{top S available players} VORP
   ```

**Prices are endogenous.** More league-wide cutting means more money chasing a
larger pool, and the price level moves in ways a fixed multiplier cannot
express. So the tool models scenarios rather than a single answer:

- **Conservative** — everyone cuts the bare minimum to reach $300
- **Expected** — everyone cuts to maximize their own surplus (fixed-point solve)
- **Aggressive** — heavy league-wide teardown

Every downstream number carries a range across those three, not a false point
estimate. The nine over-cap teams and the exact dollars each must shed are
already known (§1.2), which makes these scenarios far better grounded than
usual.

### 3.3 Cut / keep / tag optimization

Choose the retention set `R` that maximizes `Σ (price_i − salary_i)` subject to
`Σ salary_i ≤ 300` and `|R| ≤ 14`. A bounded knapsack, solved exactly by DP at
this size, with the franchise tag as an extra decision variable (one player at
prior salary ≤ $30, salary −$10, not tagged last year).

Because cuts change prices and prices change cuts, this iterates with §3.2 to a
fixed point. Output is a ranked cut list with the marginal value of each
decision, not a single take-it-or-leave-it answer.

### 3.4 Dynasty layer

Headline ranking is **2026 surplus**; multi-year value shown alongside.

```
contract_value_i = Σ_{y=0..H} discount^y × (price_{i,y} − (salary_i + 5y))
```

With `H = 3` and a discount around 0.6. The +$5/yr escalation means every
contract decays by $5 a year in real terms, which systematically favors young
ascending players and punishes expensive veterans — and makes rookie protection
(escalation-exempt for two years) worth a great deal more than it looks.

### 3.5 Steal round

Attack and defense from one model:

- **Defense:** for each of your players, `keep_price = ceil((offer − salary) × 0.85 + salary)`,
  and the offer level at which keeping stops being worth it.
- **Attack:** across all 11 other rosters, rank players by surplus (`price − salary`),
  then find the offer that maximizes *your* expected value given that a rational
  owner keeps whenever `keep_price < price`. You want players who are cheap
  relative to market held by owners who are cap-squeezed — and §1.2 tells you
  exactly who those owners are.
- Losing a player to a steal returns a second franchise tag, which has real
  value and belongs in the calculus.

### 3.6 Live auction assistant

Built for 8/24, 8–11pm, in person, entering every bid by hand:

- **Sub-two-second entry** — player, price, team, one keystroke path, undo.
- **Live cap and slot tracking for all 12 teams.**
- **Max bid** = `my_cap − (slots_left − 1)`, computed for you *and for every
  opponent*, so you know who can actually outbid you.
- **Inflation tracking** — money remaining vs. value remaining, repricing the
  board after every sale.
- **Walk-away price precomputed per player.** Rule 5.7.2 makes this a
  *sequential elimination auction*: bidding goes clockwise and **opting out is
  permanent**. You cannot re-enter after thinking better of it, so the decision
  must be made before bidding opens, not during. The app shows a hard number.
- **Nomination strategy** — which players to put up while opponents still have
  money, given that you nominate on a fixed clockwise rotation.

---

## 4. Delivery plan

Sequenced against the calendar; each phase ships before the deadline it serves.

### Deliverable 0 — Steal-round analysis (by Fri 7/31, ahead of 8/3)

Written analysis, no UI. Ranked steal targets across the other 11 rosters with
recommended offer amounts, plus a defense sheet for your own players showing
keep-prices and walk-away points. Built on throwaway scripts that become the
Phase 1 test fixtures.

*Blocked on the open questions in §6 — chiefly whether you hold a 2026 steal
pick and where it falls in the order.*

### Phase 1 — Data + valuation engine (8/1 – 8/8)

Headless and fully tested. FFL-NY league config; MFL export ingestion; the
contract lifecycle; 0.5 PPR projections; market-clearing auction pricing with
the three scenarios; the dynasty layer. Verified by re-deriving the current
rosters and checking that total value equals total money.

### Phase 2 — Cut/keep optimizer + desktop shell v1 ✅

Serves the **8/17** deadline. Shipped: the pywebview shell over a local
FastAPI server, roster and league cap views, scenario switching, and the
keep/cut/franchise-tag optimizer solved jointly — the tag is a decision
variable inside the retention knapsack, because a $10 discount changes both
whether a contract is worth keeping and how much cap is left for the others.

Every figure is overridable: click any contract to keep or cut it and the
market re-solves, since your own releases add money and players to the
auction. `Apply recommendation` takes the optimizer's plan wholesale.

### Phase 3 — Live auction assistant (8/17 – 8/23) ← next

Serves **8/24**. Bid entry, live cap and roster tracking for all 12 teams,
dynamic inflation-adjusted pricing, precomputed walk-away prices, nomination
queue. **Rehearsed against a full mock auction before draft night**, plus a
paper fallback sheet in case the laptop dies.

### Phase 4 — In-season (post-draft)

Waiver bid valuation under the blind-auction rules, lineup optimizer against
the 9-starter format, trade evaluator including the 10% receiving discount, and
tracking toward next year's escalation and steal round.

---

## 5. Risks

| Risk | Mitigation |
|---|---|
| **Phase 3 lands 24h before an irreversible 3-hour event** | Full mock-auction rehearsal in Phase 3; printed fallback board; auto-save after every bid |
| **Rosters shift constantly until 8/17** | Ingestion is re-runnable and idempotent; every number recomputes from current state |
| **An updated ETR sheet arrives close to the draft** | Alias-based column matching already tolerates renames; swapping the file is a re-import, not a code change |
| **Cut-scenario assumptions are wrong** | Three scenarios and sensitivity ranges instead of point estimates; the nine forced sellers are known, which anchors them |
| **Rules were mis-transcribed from a mangled export** | `league-rules.md` cites section numbers throughout; §6 items confirmed with the commissioner before the app acts on them |
| **MFL export format is unknown** | Import layer is written defensively against a sample export; the workbook path stays as a fallback |

---

## 6. Open questions

Most of the original blockers were answered by re-parsing the sheet's asset
tables positionally — see
[`2026-offseason-decisions.md`](./2026-offseason-decisions.md). Resolved:
steal pick **#8 of 12**; **1** franchise tag owned outright; **no** active
rookie protections and **no** 2025 tag, so rule 6.3 binds nothing; the four
steal-proof players league-wide; and the posture — **rebuild while competing**,
which sets the §3.4 dynasty weighting toward future seasons.

Still open, in priority order:

1. **Is the franchise tag's ≤$30 limit (6.1) actually enforced for 2026?** Every
   2025 tag in the sheet violates it. It does not change this year's
   recommendation, but the engine must encode the right rule.
2. **Confirm the ownership lineage.** The 2025 rookie-protection table lists
   *Mike* where the 2026 asset table lists *Andrew*; a separate, unrelated
   "Andrew" held a different franchise 2020–2024. This determines whose tag
   history binds you.
3. **Can you export a sample MFL CSV** (rosters + salaries) so the import layer
   is built against the real format rather than a guess?
4. **Which OS?** pywebview covers macOS and Windows; it only affects packaging.
5. **Did any rules change in the 5/18/26 vote** that the exported sheet doesn't
   reflect?
