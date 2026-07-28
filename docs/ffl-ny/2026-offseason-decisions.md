# FFL-NY 2026 — Offseason Decision Analysis (Andrew's Team)

Covers the three decisions due before the auction: the **8/3 steal round**, the
**8/17 franchise tag**, and the **8/17 cut list**.

All dollar figures come from a first-pass market model (§5). Treat the
*direction* as reliable and the *precision* as not.

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

**Recommendation: tag Jameson Williams, $18 → $8.**

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

### The mechanic works against the attacker

To pry a player loose you must push the keep price above what he is worth to his
owner. Since `keep_price = ceil((offer − salary) × 0.85 + salary)`, that requires

```
offer ≥ salary + (market − salary) / 0.85
```

At that number **you are paying above market**. Against a rational, cap-healthy
owner, a steal cannot generate surplus. The value comes from two other places:

1. **Cap-squeezed owners.** Nine of twelve teams are over the cap and must shed
   salary by 8/17 regardless. For them, surrendering a player is relief, not
   loss — so they let go below the theoretical threshold.
2. **A failed steal still lands.** If they keep, their salary rises by
   `(offer − salary) × 0.85`, which is real damage to a team that must already
   cut.

### Sequencing is in your favour

The steal round is **8/3**; the cap-compliance deadline is **8/17**. You do not
need cap room on Monday — only by the 17th. Your effective steal budget is the
**full $300**, not your current −$66.

### Targets, ranked by surplus and owner distress

| Player | Pos | Owner | Salary | Market | Surplus | Pry price | Owner over cap |
|---|---|---|---:|---:|---:|---:|---:|
| **Trey McBride** | TE | Tire Fire Sale | 14 | 38 | +24 | 42 | **$80** |
| **Rashee Rice** | WR | Tire Fire Sale | 15 | 35 | +20 | 39 | **$80** |
| **Terry McLaurin** | WR | Tire Fire Sale | 10 | 27 | +17 | 30 | **$80** |
| Christian McCaffrey | RB | Tire Fire Sale | 47 | 71 | +24 | 75 | **$80** |
| Luther Burden | WR | Joseph the Tank | 8 | 25 | +17 | 28 | $70 |
| Colston Loveland | TE | Joseph the Tank | 16 | 29 | +13 | 32 | $70 |
| Puka Nacua | WR | The MidDermott's | 56 | 80 | +24 | 85 | $51 |
| Justin Jefferson | WR | Pink Pony Club | 53 | 67 | +14 | 70 | $63 |
| Jaxon Smith-Njigba | WR | Team X-Blades | 27 | 80 | **+53** | 90 | $0 |
| Javonte Williams | RB | Team X-Blades | 11 | 35 | +24 | 40 | $0 |

**Primary: Trey McBride at ~$42.** Best combination of surplus, age, and owner
distress. RJ is $80 over the cap carrying 15 players and must gut the roster
anyway; a $24 salary bump on a player he is already struggling to afford is
punishing. Either you get a top-two dynasty TE at $42, or the league's strongest
roster absorbs another $24 of cap damage. Both outcomes are good for you.

**Note on Smith-Njigba:** by far the largest surplus, but Lawless is *under* the
cap and can comfortably keep him, so the $90 pry price is real. At market ~$80
it is only a ~$10 overpay for a 24-year-old WR1 — defensible in a dynasty
rebuild, but it consumes 30% of your cap. Take it only if the cheaper targets
are gone.

**Have contingencies ready.** Seven owners steal before you.

---

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

1. **Tag Jameson Williams** ($18 → $8) and keep him.
2. **Cut the other thirteen.** Enter the auction with **$292**.
3. **Steal McBride at ~$42** on 8/3 — before the drop deadline, so the cap cost
   lands after your cuts.
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
