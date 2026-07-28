# FFL-NY ("HARD STUFF") — Operative Rules Reference

Condensed from the shared Google Sheet *FFL-NY League Rules*, retaining the
rules that the app has to model. Section numbers match the source sheet, so
anything here can be traced back. Historical trade/steal logs and the weekly
schedule grid are deliberately omitted.

The source sheet is a rules-voting worksheet with heavy merged-cell
duplication; it is close to unreadable as exported. This file is the working
reference. **Re-verify against the sheet before the app acts on any rule** —
rules are voted on annually (proposals 5/10, voting 5/18).

## League shape

| | |
|---|---|
| Teams | 12, in 2 conferences of 6 (2.1) |
| Regular season | 14 weeks, then 3 playoff weeks (2.2) |
| Playoff field | 6 teams — conference winners get a bye (4.1, 4.2.1) |
| Platform | MyFantasyLeague (10.4, 14.1.2) |
| Entry | $100/yr (11.1) |

## Roster and lineup

- **Starters (1.1):** 1 QB, 2 RB, 2 WR, 1 TE, 2 FLEX (RB/WR/TE), 1 DEF = **9 starters**.
- **No kicker.** There is no K slot and no kicker scoring anywhere in §3.4.
- **Max roster (1.4):** **14** in the regular season; **15** in playoffs and offseason.
- **Min roster (1.3):** 9 — enough to field a legal lineup — from the auction until the team's season ends.
- Roster-composition rules are **suspended during the offseason** (1.2, 13.1.4): no position minimums, no roster floor.

## Scoring (3.4) — half PPR

| Offense | | Defense/ST | |
|---|---|---|---|
| Passing TD | 4 | Sack | 1 |
| Passing yards | 1 / 25 | Safety | 2 |
| Passing 2pt | 2 | Interception | 2 |
| Interception | −2 | Fumble recovery | 2 |
| Rush/Rec TD | 6 | Blocked kick | 2 |
| Rush/Rec yards | 1 / 10 | Def/ST TD | 6 |
| **Reception** | **0.5** | ST fumble lost | −2 |
| Lost fumble | −2 | XP block return / failed 2pt return | 2 |

Defensive points allowed: 0 → 5; 1–6 → 4; 7–13 → 3; 14–17 → 1; 18–27 → 0;
28–34 → −1; 35–45 → −3; 46+ → −5.

Defensive yards allowed: <100 → 5; 100–199 → 3; 200–299 → 2; 350–399 → −1;
400–449 → −3; 450–499 → −5; 500–549 → −6; 550+ → −7.

Fractional scoring throughout. ESPN's scoring system is the tiebreaking
authority on any ambiguity (3.2).

> **Modeling note:** receptions are **0.5**, so the ETR sheet's *Half PPR*
> column is the correct input — not Full PPR.

## Salary cap and the contract lifecycle

This is the part that makes the league unusual, and it is most of what the app
has to get right.

- **Cap: $300** per team for the auction (5.1). Spending it all is optional.
- **Annual escalation (14.2):** after the Super Bowl, **every player on your
  roster gains +$5** for the next season. Rookie-protected players are exempt.
  Owners may keep or drop as many players as they like.
- **In-season salary changes (9.3):** a salary only moves by being **dropped**
  (salary voids; resets to the winning bid if re-acquired on waivers) or
  **traded for the first time**.
- **Trade discount (10.2):** the receiving team gets a **one-time-per-season
  10% reduction**: `Salary = Round(Current × 0.9, 0)`.
- **Franchise tag (6.1–6.3):** one player per year (two if you hold a second
  tag) whose **previous-season salary was ≤ $30**; the tag **drops his salary
  by $10**. Cannot be applied to the same player in consecutive years. Never
  more than 2 tags held. Since 2024, **a franchise tag does not protect
  against steal attempts** (15.2).
- **Rookie protection (7.1–7.4):** immediately after the auction, designate a
  rookie drafted in that auction whose salary is ≤ $30. He is exempt from
  salary escalation **and** steal attempts for his rookie season plus one more.
  He must not be dropped or traded. Max 2 protected rookies at a time.
- **Jordy Nelson rule (14.3):** a player who lands on IR, dies, or officially
  retires between the drop deadline and the draft may be dropped. He remains
  draftable.

## Steal round (15.1–15.7)

Each owner gets **one steal offer** per offseason, in an order set by the prior
season's finish (§4). The consolation bracket inverts as you would expect: the
best aggregate scorer among the 7th–12th place teams gets the **1st** steal
pick; the champion gets the **12th**.

- The offer must be **≥ the player's current salary** (15.5).
- The player's current owner then chooses:
  - **Let him go** — he joins the bidder at the offer price, and the losing
    owner receives a **second franchise tag**, which must be used, traded, or
    forfeited next season (15.6).
  - **Keep him** — at a new salary of (15.4):

    ```
    keep_price = ceil((offer − current_salary) × 0.85 + current_salary)
    ```

> **Modeling note:** the keep formula means a steal offer is never free to the
> defender — every dollar above the current salary costs him 85 cents. The
> attacker's leverage is highest against players who are *underpriced relative
> to market*, because the defender must either overpay or surrender surplus.

## Auction draft (5.1–5.9)

- **Nomination order (5.5):** a random draw sets the opening nominator; after
  that it proceeds **clockwise by seating order**, round after round.
- **Opening bid (5.7.1):** the nominating owner must open at **≥ $1**, and may
  open higher.
- **Bidding (5.7.2):** bidding proceeds **clockwise in rounds**. On your turn
  you either raise by ≥ $1 or **opt out — and opting out is permanent for that
  player**. Bidding continues round by round until one owner remains. You may
  not change a bid once the next owner has acted.
- **Roster requirement (5.2):** you must be able to field a full lineup (§1.1)
  when the auction ends.
- **No drops or trades during the auction** (5.8, 14.1.3).
- **Leaving early (5.9):** you may leave with an incomplete roster and fill it
  with $1 players the next day, in reverse order of the prior year's standings.
- **Eligibility (5.4):** the player must be on an NFL roster or have NFL
  experience. Drafted-but-unsigned counts. No college players.

> **Modeling note:** the permanent opt-out makes this a **sequential
> elimination auction, not open outcry**. Your seat position relative to the
> nominator matters, and an early opt-out is irreversible — so the app should
> compute a walk-away price *before* bidding opens on a player, not during.

## Waivers (8.1–8.8)

- **Closed (blind) auction** twice weekly: Wednesday 11:59pm ET and Saturday
  12:00pm ET. Moves to Tuesday 11:59pm in any week with a Wednesday NFL game.
- A won player's **salary becomes the winning bid** (9.3).
- Players dropped in the preceding period are biddable in the current one (8.3).
- No player who played in a Thursday night game is eligible in that Saturday
  window (8.2.2).
- Tiebreakers (8.5): winning % → total points → head-to-head → last week's points.
  In week 1, the lowest-ranked team from the prior year wins ties (8.6).
- You must be cap- and roster-compliant **1 hour before the first game of the
  week** (8.7). The commissioner will forcibly compliant a team that is not (8.8).

## Trades (10.1–10.5, 13.1)

- Deadline: **5:00pm ET Thursday of week 13**.
- Receiving team absorbs the salary, less the one-time 10% discount (10.2).
- Steal picks and franchise tags are tradeable, including future years (10.3).
- **Not tradeable (10.5):** cap dollars, agreements to drop, agreements not to
  bid, players to be named later, postseason agreements, players you don't own.
- Offseason: teams **may exceed $300 while trading** and carry 15 players, but
  must be compliant by the drop deadline (13.1.1, 13.1.3).

## 2026 calendar

| Event | Date | Notes |
|---|---|---|
| Steal Round | **Mon 8/3/26**, 9am–5pm | Teams chat / group text / email |
| Drop, Tag & Trade Deadline | **Mon 8/17/26**, midnight | Must be ≤ $300. No drops or trades until after the auction (14.1.2). |
| **Auction Draft** | **Mon 8/24/26**, 8–11pm | In person, 124 Jamaica Rd, Tonawanda NY |
| First Waivers | Wed 9/2/26 | Only runs if the draft is >7 days before kickoff (14.1.4) |
| Season starts | Wed 9/9/26 | |

Trading is frozen from the drop deadline until the auction ends (14.1.2).

## Payouts (12.1, 12.2)

Champion 52.5%, 2nd 27.5%, 3rd 15%, 4th 5%. The lowest total scorer through
week 17 wears a league-designed shirt to the office and to postseason
functions.

## 2026 asset ownership

Recovered by re-parsing the sheet's asset table positionally — the flat export
collapses the owner columns and destroys this mapping.

| Owner | Team | 2026 steal pick | Franchise tags |
|---|---|---:|---:|
| Robison | Joseph the Tank Engine | 1 | 1 |
| Jesse | Houle's Heros | 2 | 1 |
| Bob | Slobberknocker | 3 | 1 |
| Ben | Canal Cats | 4 | 1 |
| John | The MidDermott's | 5 | 1 |
| Jeremy | Lyon in Last | 6 | 1 |
| Eric | Danheiser Dunces | 7 | **2** (compensation) |
| **Andrew** | **Andrew's Team** | **8** | **1** |
| Dan | Muff's Punters | 9 | 1 |
| Greg | Pink Pony Club | 10 | 1 |
| Lawless | Team X-Blades | 11 | 1 |
| RJ | Tire Fire Sale | 12 | **2** (compensation) |

Steal order encodes final 2025 standings (§4): RJ at 12 was champion; Robison at
1 won the consolation bracket; **Andrew's franchise at 8 finished 6th overall**.

**Steal-proof in 2026** — 2025 rookie protections held all year, so exempt from
both escalation and steal attempts (7.3): Travis Hunter ($28, Robison), Emeka
Egbuka ($20, RJ), Tyler Warren ($14, Jesse), Bhayshul Tuten ($1, John). Tuten
sitting at $1 while every other minimum contract escalated to $6 confirms the
exemption is applied in practice.

**2025 franchise tags used:** John–Pearsall, Robison–Collins, Ben–Hurts,
Jesse–Waddle, RJ–Mahomes & Rice, Eric–Hubbard, Greg–Jefferson,
Lawless–Smith-Njigba, Dan–Achane, Jeremy–Burrow & Sutton. Andrew's franchise
used none, so rule 6.3's consecutive-year bar restricts nothing in 2026.

## Open items to confirm with the commissioner

1. **Is 6.1's ≤$30 franchise-tag limit in force for 2026?** Every 2025 tag
   listed above exceeds it — Jefferson $58, Achane $62, Collins $50,
   Smith-Njigba $32 — so the limit is either new this year or has not been
   enforced. Rule 6.1 is marked APPROVED and carries a footnote about
   commissioner review and revocation, which reads like new enforcement.
2. **Ownership lineage of Andrew's Team.** The 2025 rookie-protection table
   lists *Mike* in the slot the 2026 asset table assigns to *Andrew*; a separate
   "Andrew" held a different franchise 2020–2024 and left after that season.
3. **Whether any rule changes passed in the 5/18/26 vote** are reflected in the
   sheet as exported.
