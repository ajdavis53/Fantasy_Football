"""Generate a printable auction board, for when the laptop is not an option.

The draft is three hours in somebody's living room. Laptops die, wifi is
irrelevant but power is not, and a crash at 9pm with two hours of bidding left
would be unrecoverable. This produces a single sheet you can print beforehand
and bid from on paper: the ranked board with par prices, a max-bid ready
reckoner, and blank columns to write sales into.

    uv run python scripts/fallback_board.py rosters.xlsx etr.csv -o board.html

Then print it from a browser. Deliberately an HTML file rather than a PDF:
there is no PDF dependency in this project, every machine can already print a
web page, and the styling stays editable if a column turns out to be in the
wrong place at the table.

The prices are par, not inflation-adjusted -- on paper you cannot recompute
after every sale. The ready reckoner is the substitute: it is the arithmetic
you would otherwise get wrong under time pressure.
"""
from __future__ import annotations

import argparse
import html
from pathlib import Path

from app.session import Session
from engine.auction import max_affordable_bid

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LEAGUE = ROOT / "config" / "leagues" / "ffl_ny.yaml"

STYLE = """
@page { size: A4 portrait; margin: 10mm; }
* { box-sizing: border-box; }
body { font: 9pt/1.25 ui-sans-serif, system-ui, sans-serif; color: #000; margin: 0; }
h1 { font-size: 14pt; margin: 0 0 2mm; }
h2 { font-size: 10pt; margin: 4mm 0 1.5mm; text-transform: uppercase; letter-spacing: .05em; }
p.note { font-size: 8pt; color: #444; margin: 0 0 2mm; }
table { width: 100%; border-collapse: collapse; }
th, td { border: 1px solid #999; padding: 1mm 1.5mm; text-align: left; }
th { background: #eee; font-size: 8pt; text-transform: uppercase; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
td.write { background: #fafafa; min-width: 16mm; }
tr:nth-child(even) td { background: #f6f6f6; }
tr:nth-child(even) td.write { background: #fafafa; }
.side { display: flex; gap: 4mm; align-items: flex-start; }
.side > * { flex: 1; }
.rules { font-size: 8pt; border: 1px solid #999; padding: 2mm; }
.rules li { margin-bottom: 1mm; }
.pagebreak { page-break-before: always; }
"""


def render(session: Session, rows: int) -> str:
    rules = session.rules
    auction = session.start_auction()
    me = auction.status(session.my_team)
    board = auction.board(limit=rows)

    def esc(value: object) -> str:
        return html.escape(str(value))

    # Max bid is budget less $1 per slot still to fill (5.2). Easy arithmetic,
    # easy to fumble at 10pm with people talking over you.
    reckoner = "".join(
        f"<tr><td class='num'>{slots}</td>"
        + "".join(
            f"<td class='num'>{max_affordable_bid(budget, slots, rules.min_bid)}</td>"
            for budget in (50, 100, 150, 200, 250, 300)
        )
        + "</tr>"
        for slots in range(1, rules.max_roster + 1)
    )

    board_rows = "".join(
        f"<tr><td>{esc(a.player.name)}</td><td>{esc(a.player.position)}</td>"
        f"<td>{esc(a.player.nfl_team or '')}</td>"
        f"<td class='num'>{a.par:.0f}</td>"
        f"<td class='num'>{a.next_best_gap:.0f}</td>"
        f"<td class='write'></td><td class='write'></td></tr>"
        for a in board
    )

    teams = "".join(
        f"<tr><td>{esc(s.team)}{' (you)' if s.is_me else ''}</td>"
        f"<td class='num'>{s.budget}</td><td class='num'>{s.slots_to_fill}</td>"
        f"<td class='num'>{s.max_bid}</td>"
        + "".join("<td class='write'></td>" for _ in range(4))
        + "</tr>"
        for s in auction.all_status()
    )

    source = (
        f"post-deadline rosters from {Path(session.post_deadline_source).name}"
        if session.post_deadline_source
        else "rivals' rosters are PROJECTED, not final"
    )

    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>{esc(session.league.name)} auction — paper board</title>
<style>{STYLE}</style></head><body>

<h1>{esc(session.league.name)} auction &mdash; {esc(session.my_team)}</h1>
<p class="note">
  Opening budget <strong>${me.budget}</strong> &middot; {me.slots_to_fill} slots to fill
  &middot; opening max bid <strong>${me.max_bid}</strong>
  &middot; ${auction.remaining_dollars():,} and {auction.remaining_slots()} slots in the room
  &middot; {esc(source)}
</p>

<div class="side">
  <div>
    <h2>Max bid by budget and slots left</h2>
    <p class="note">Rule 5.2: you must field a full lineup, so reserve $1 per unfilled slot.</p>
    <table>
      <tr><th class="num">Slots</th>{"".join(f"<th class='num'>${b}</th>" for b in (50,100,150,200,250,300))}</tr>
      {reckoner}
    </table>
  </div>
  <div class="rules">
    <h2>At the table</h2>
    <ul>
      <li><strong>Opting out is permanent</strong> (5.7.2). Bidding goes clockwise in
          rounds; once you pass on a player you cannot re-enter. Decide the
          walk-away number before bidding opens.</li>
      <li>Opening bid is at least $1 (5.7.1); the nominator sets it.</li>
      <li>No drops or trades during the auction (5.8).</li>
      <li>You may leave early with an incomplete roster and fill at $1 the next
          day (5.9), in reverse order of last year's standings.</li>
      <li>Right after the auction, designate up to two drafted rookies at
          &le;${rules.rookie_protection_max_salary} as protected (7.1): no
          escalation and no steal attempts for two seasons.</li>
      <li>Nominate players you do <em>not</em> want while rivals still have money.</li>
    </ul>
  </div>
</div>

<h2>Board &mdash; par prices</h2>
<p class="note">
  Par assumes the whole board clears at these prices. If the room overpays early,
  everything later goes cheaper than par; if it sits still, dearer. Drop is what the
  next player down at the same position costs you.
</p>
<table>
  <tr><th>Player</th><th>Pos</th><th>Tm</th><th class="num">Par</th>
      <th class="num">Drop</th><th>Sold for</th><th>To</th></tr>
  {board_rows}
</table>

<div class="pagebreak"></div>
<h2>Room &mdash; track budgets as they spend</h2>
<p class="note">Cross out and rewrite. What matters is who can still outbid you.</p>
<table>
  <tr><th>Team</th><th class="num">Budget</th><th class="num">Slots</th><th class="num">Max bid</th>
      <th>after</th><th>after</th><th>after</th><th>after</th></tr>
  {teams}
</table>
</body></html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roster", type=Path)
    parser.add_argument("etr", type=Path)
    parser.add_argument("-o", "--out", type=Path, default=ROOT / "data" / "cache" / "paper_board.html")
    parser.add_argument("--league", type=Path, default=DEFAULT_LEAGUE)
    parser.add_argument("--team", default="Andrew's Team")
    parser.add_argument("--post-deadline", type=Path, default=None)
    parser.add_argument("--rows", type=int, default=90, help="players to print")
    parser.add_argument("--apply", action="store_true",
                        help="apply the optimizer's cut plan before building the board")
    args = parser.parse_args()

    session = Session.load(args.league, args.roster, args.etr, my_team=args.team)
    if args.post_deadline:
        for issue in session.adopt_post_deadline_rosters(args.post_deadline):
            print(f"  warning: {issue}")
    elif args.apply:
        session.apply_recommendation()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(session, args.rows))
    print(f"wrote {args.out}  ({args.rows} players)")
    print("open it in a browser and print to paper or PDF")


if __name__ == "__main__":
    main()
