# FFL-NY 2026 — Offseason Decision Analysis (Andrew's Team)

Covers the three decisions due before the auction: the **8/3 steal round**, the
**8/17 franchise tag**, and the **8/17 cut list**.

All dollar figures come from the market model in `engine/` (§6). Treat the
*direction* as reliable and the *precision* as not. §4 has been regenerated
from the engine; the rest is the original analysis and matches it closely.

---

## 1. What the franchise already holds

Recovered from the rules sheet's 2026 asset table, which the plain export
mangles — the owner columns had to be re-parsed positionally.

| | |
|---|---|
| 2026 steal pick | **#8 of 12** |
| 2026 franchise tags | **1**, owned outright |
| Active rookie protections | **none** |
| 2025 franchise tag used | **none** |

Two rivals hold **two** tags each — **Eric (Danheiser Dunces)** and **RJ (Tire
Fire Sale)** — each having received a compensation tag for losing a player to a
steal. They can protect two players apiece this year.

**Full 2026 steal order:** Robison 1, Jesse 2, Bob 3, Ben 4, John 5, Jeremy 6,
Eric 7, **Andrew 8**, Dan 9, Greg 10, Lawless 11, RJ 12.

> **The franchise finished 6th overall in 2025.** Steal pick 8 is awarded to the
> loser of the week-16 fifth-place game (rule 4.2.3), which means this team made
> the playoffs as a wild card, lost, and lost the consolation game. It is a
> recent playoff roster that has aged badly and is now deeply cap-underwater —
> not a bottom-feeder.

### Ownership lineage

The 2025 rookie-protection table lists **MIKE** in the slot the 2026 asset table
assigns to **Andrew**, so this franchise passed from Mike to you. An earlier,
unrelated "Andrew" held a *different* franchise from 2020–2024 and left after
that season; do not read that history as yours. Worth a sentence of confirmation
with the commissioner, since it determines whose tag/protection history binds
you.

---

## 2. Franchise tag — what applies before it is set

Nothing constrains you from rule 6.3: this franchise used **no 2025 tag**, so
the consecutive-year bar is inactive and every eligible player is available.

The live constraint is **rule 6.1**: the player's *previous-season* value must be
**≤ $30**. Since every retained player took the +$5 escalation (14.2), that means
a current salary of **≤ $35**.

| Eligible (≤$35 now) | Not eligible |
|---|---|
| Jauan Jennings $26, J. Williams $18, Dak Prescott $17, AJ Barner $16, Isaiah Likely $16, Dalton Schultz $16, Kareem Hunt $15, Dallas Goedert $14, Devin Singletary $10, Chris Godwin $8, DAL DEF $8 | Saquon Barkley $86, Davante Adams $61, A.J. Brown $55 |

**Recommendation: tag Jameson Williams, $18 → $8 — and do it before 8/3.**

He is the only contract on the roster carrying positive surplus, and the tag
roughly triples it (market ≈ $25). Every other eligible player is at or below
replacement level, where a $10 discount buys nothing.

> ⚠️ **Confirm the ≤$30 limit is actually in force.** Every 2025 tag in the
> sheet violates it — Jefferson $58, Achane $62, Collins $50, Smith-Njigba $32 —
> so it is either new for 2026 or historically unenforced. Rule 6.1 is marked
> APPROVED and carries a pointed footnote about commissioner review and
> revocation, which reads like new enforcement. It happens not to change the
> recommendation: even unconstrained, tagging Barkley ($86→$76 against a ~$75
> market) or Adams ($61→$51 against ~$35) buys nothing.

## 3. Rookie protection — a draft-day decision, not a current one

Rule 7.1 restricts the designation to **a rookie drafted in that year's
auction**, so no current roster player can receive it. Nothing to set before
8/17.

**But plan for it on 8/24.** You hold **both** protection slots (max 2, rule
7.4.2) and have none in use. A rookie bought at ≤$30 and held becomes exempt
from **both** salary escalation and steal attempts for 2026 *and* 2027 — a
frozen, steal-proof contract for two years, in a league where every other
contract inflates $5 a year. For a rebuild that is the single most valuable
mechanism in the rulebook, and it is free.

Evidence it works as written: **Bhayshul Tuten sits at $1** on The MidDermott's,
having been protected as a 2025 rookie. Every other minimum contract in the
league escalated to $6.

### Steal-proof players in 2026

2025 rookie protections held all year, so they are exempt from steal attempts
this round. Do not waste pick 8 on them:

| Player | Pos | Salary | Team |
|---|---|---:|---|
| Travis Hunter | WR | $28 | Joseph the Tank Engine |
| Emeka Egbuka | WR | $20 | Tire Fire Sale |
| Tyler Warren | TE | $14 | Houle's Heros |
| Bhayshul Tuten | RB | $1 | The MidDermott's |

---

## 4. Steal round — Monday 8/3, pick 8

*Regenerated from the engine (`scripts/steal_report.py`), which computes pry
prices exactly rather than from the closed form. The figures below supersede
the first pass; where they differ it is by a dollar or two of rounding, plus
one larger change explained under sensitivity.*

### The mechanic works against the attacker

To pry a player loose you must push the keep price above what he is worth to
his owner. Since `keep_price = ceil((offer − salary) × 0.85 + salary)`, the
defender absorbs only 85 cents of each dollar of premium — so the offer that
finally breaks him is **always above the player's market value**. Against a
rational, cap-healthy owner a steal cannot generate surplus. That is not a
quirk of these numbers; it is what the formula guarantees.

### Sensitivity: the entire value case rests on one assumption

Nine of twelve teams must shed salary by 8/17. The model assumes an owner in
that position values his own contract *below* market, because keeping it forces
a cut elsewhere — up to 30% below, scaled by how far over the cap he is. Change
that one assumption and the conclusion inverts:

| Assumption | Best target | Value per dollar |
|---|---|---:|
| Owners are distressed (30% cap) | McCaffrey at $53 | **1.35** |
| Owners value at full market | *nothing* | **≤ 1.00** |

At zero distress the whole board collapses to 1.00 or below — the formula's
guarantee reasserting itself. So the question is not "which player" but
"how squeezed are these twelve people, really". That is a judgement about
people, not something the model can settle. The table below assumes they are
squeezed; discount it accordingly.

### Targets

Ranked at the pry price, assuming distress. `$/$` is value per dollar — the
auction clears at market, so a dollar spent bidding buys a dollar of value, and
anything at or below 1.00 means you should simply bid instead.

| Player | Pos | Owner | Salary | Value | Pry | Damage if kept | $/$ |
|---|---|---|---:|---:|---:|---:|---:|
| **Christian McCaffrey** | RB | Tire Fire Sale | 47 | 72 | **53** | 6 | **1.35** |
| Trey McBride | TE | Tire Fire Sale | 14 | 38 | **30** | **14** | 1.27 |
| Rashee Rice | WR | Tire Fire Sale | 15 | 36 | **28** | 12 | 1.27 |
| Justin Jefferson | WR | Pink Pony Club | 53 | 68 | 54 | 1 | 1.26 |
| Colston Loveland | TE | Joseph the Tank | 16 | 30 | 24 | 7 | 1.24 |
| Terry McLaurin | WR | Tire Fire Sale | 10 | 27 | 22 | 11 | 1.24 |
| DeVonta Smith | WR | Muff's Punters | 27 | 33 | 27 | 0 | 1.23 |
| Luther Burden | WR | Joseph the Tank | 8 | 25 | 21 | 12 | 1.19 |
| Puka Nacua | WR | The MidDermott's | 56 | 81 | 69 | 12 | 1.18 |
| Brock Bowers | TE | The MidDermott's | 26 | 39 | 34 | 7 | 1.15 |

**Four of the top seven sit on Tire Fire Sale.** RJ is $80 over the cap
carrying 15 players — the most distressed owner in the league and the one this
model therefore discounts hardest. That concentration is a feature of the
assumption as much as of his roster; treat it as a reason to check the
assumption, not as confirmation.

### One offer, one number

A steal is a single sealed offer, so the ladder collapses to a choice about
what you believe:

- **McBride at $30** — if RJ is as squeezed as the cap table suggests, he lets
  go and you have a top-two dynasty TE at $30 against a $38 market. If he is
  not, he keeps him and absorbs **+$14 of salary** he can ill afford.
- **McBride at $43** — the price at which he lets go even valuing at full
  market. You would be paying $5 above market for the certainty.

The floor under either is the same: RJ's cap gets worse. That part does not
depend on the distress assumption at all.

### Sequencing and depth

Seven owners choose before you — Robison, Jesse, Bob, Ben, John, Jeremy, Eric
— so plan **seven deep**. The steal round is 8/3 and cap compliance is not due
until 8/17, so you do not need room on Monday: your effective budget is the
full **$300**, not your current −$66.

### Your own exposure

After the recommended teardown you hold one contract, so there is almost
nothing to defend: **Jameson Williams**, tagged to $8 against a ~$25 market.
Someone must offer **$27** to pry him, and keeping him would then cost you $25.

### Apply the tag before 8/3, not at the deadline

Rule 6.1 permits the franchise tag any time up to the drop deadline, so it can
be applied *before* the steal round — and it should be. A lower salary makes a
player **harder** to steal, because the keep price climbs from a lower base at
only 85 cents per dollar:

| Jameson Williams | Salary | Offer needed to pry |
|---|---:|---:|
| Untagged | $18 | $26 |
| Tagged before 8/3 | $8 | **$27** |

It is one dollar at his valuation — marginal, but free, and it runs the
opposite way to the intuition that a cheap contract is an easy target. On a
more valuable player the same effect is worth considerably more.

### What this pick is actually for

Given the teardown leaves you with the largest auction budget in a league where
nine teams are cap-crippled, your money works hardest *at the auction*, where
the clearing price is market by construction and you have a structural edge.
A steal, by contrast, is guaranteed to cost above market against any owner who
is thinking clearly.

So the reliable value in pick 8 is **the damage**, not the player: forcing the
league's strongest roster to absorb another $14 of salary it must already shed.
McBride at $30 does that whether or not RJ takes the bait. Treat any actual
acquisition as the upside case rather than the plan.

## 5. The cut list — "drop everyone" is close to right

### Your roster carries essentially no surplus

Under the equilibrium market model, **exactly one contract is worth keeping**:

| Player | Pos | Salary | Market | Surplus |
|---|---|---:|---:|---:|
| **Jameson Williams** | WR | 18 | ~25 | **+7** (→ +17 tagged) |
| Everyone else | | 348 | | ≤ 0 |

$62 across four tight ends when you start one; three non-cheap running backs;
Barkley at $86 and Adams at $61 against markets well below that. There is no
version of this roster worth defending.

### But the *value* of dropping depends on what everyone else does

This is the part the raw surplus numbers hide. Auction prices are endogenous —
the money and the player pool are both produced by twelve simultaneous cut
decisions. Two bracketing scenarios:

| | Auction $ | Slots | Avg/slot | **Your share if you drop everything** |
|---|---:|---:|---:|---:|
| **Minimum cuts** (teams shed only what the cap demands) | $313 | 9 | $35 | **51%** |
| **Full teardown** (every unprofitable contract cut) | $2,770 | 129 | $22 | **11%** |

In the minimum-cut world you would control **more than half of every dollar in
the auction**, against eleven rivals whose largest individual war chest is about
$50. You could buy essentially any player who hits the block, at a price set by
a bidder who cannot exceed $50. In the teardown world you are simply one of
twelve well-funded bidders.

**Dropping is right in both worlds** — dominant in one, neutral in the other —
and keeping is wrong in both. That asymmetry, not the surplus arithmetic, is the
real argument.

Reality will land in between: owners are loss-averse and rarely tear down fully,
so expect $400–$1,200 of total auction money and a 25–50% share for you.

### One correction to the premise

You will **not** get your own players back at a discount. Dropped players enter
an open auction and get priced at market like everyone else. What you actually
buy with a teardown is **the money and the flexibility** — and, in a league where
nine of twelve teams are cap-crippled, being the only owner with real money is
worth far more than any of these contracts.

### Recommendation

1. **Tag Jameson Williams** ($18 → $8) and keep him — before the 8/3 steal
   round, which makes him marginally harder to steal (§4).
2. **Cut the other thirteen.** Enter the auction with **$292**.
3. **Steal McBride at $30** on 8/3 — before the drop deadline, so the cap cost
   lands after your cuts. If he stays, RJ absorbs $14 he cannot afford (§4).
4. **At the auction, buy two rookies at ≤$30 and protect both** — steal-proof,
   escalation-frozen through 2027.

That is a rebuild that still competes: you would field a young core plus
whatever the auction's distressed sellers give up, with the league's largest
budget and two protected contracts. Realistic expectation for 2026 is
bubble-to-wild-card, with 2027 as the real target.

### Practical risk at the auction

The draft runs **8–11pm, three hours**. Buying 13–14 players in one night while
rivals buy two or three each is a real operational load, and the good players go
early while opponents still have money. Two mitigations, both worth building
into the app:

- Rule 5.6 keeps rounds running until rosters are complete, so late in the night
  you may be nominating essentially unopposed at $1 — plan to fill depth then,
  not early.
- Rule 5.9 lets you leave with an incomplete roster and fill at $1 the next day.

---

## 6. Model caveats

The market values are back-solved from ETR's Half PPR column: `VORP ≈ value − $1`
under ETR's own market clearing, re-cleared against FFL-NY's actual dollars,
slots, and pool. This is a first pass, and it is wrong in known ways:

- **ETR's roster construction is not this league's** (2 FLEX, DEF, no K, 14-man
  rosters). Positional replacement levels will shift once Phase 1 refits
  projections under FFL-NY scoring.
- **These are redraft values, not dynasty values.** No age curve, no multi-year
  contract value. That systematically undervalues young players — Smith-Njigba,
  McBride, Burden, Loveland — and overvalues aging veterans. The dynasty layer
  (PLAN §3.4) is what corrects this, and it will likely *strengthen* the case for
  the young steal targets.
- **The equilibrium assumes rational simultaneous cutting.** Real owners anchor
  on what they paid.
- ETR values are also pre-camp; an updated sheet before 8/24 should be re-run.
