"""Generate a small sample rankings workbook for smoke-testing the UI.

This is DEMO DATA, not a rankings product: the top rows carry real ETR ranks
and ADP for recognisable players so the layout can be judged at realistic
widths, and the tail is generated filler to give the board enough depth to
run a full draft. Never draft off this file -- point the app at your own ETR
export instead.

    uv run python scripts/make_sample_rankings.py data/sample_rankings.xlsx
"""
from __future__ import annotations

import sys

import openpyxl

HEADERS = ["Rank", "Player", "Pos", "Team", "Pos Rank", "ADP", "Rank Diff", "ADP Pos Rank", "Pos Rank Diff"]

# (name, pos, team, adp) at their real ETR ranks, in order.
REAL_TOP = [
    ("Jahmyr Gibbs", "RB", "DET", 1.3), ("Bijan Robinson", "RB", "ATL", 1.7),
    ("Puka Nacua", "WR", "LA", 4.0), ("Ja'Marr Chase", "WR", "CIN", 3.0),
    ("Jaxon Smith-Njigba", "WR", "SEA", 5.0), ("Christian McCaffrey", "RB", "SF", 6.3),
    ("Justin Jefferson", "WR", "MIN", 10.3), ("Amon-Ra St Brown", "WR", "DET", 7.7),
    ("Jonathan Taylor", "RB", "IND", 8.3), ("CeeDee Lamb", "WR", "DAL", 10.0),
    ("Saquon Barkley", "RB", "PHI", 16.3), ("James Cook", "RB", "BUF", 10.7),
    ("Ashton Jeanty", "RB", "LV", 10.3), ("Drake London", "WR", "ATL", 16.3),
    ("Kenneth Walker", "RB", "KC", 15.3), ("Chase Brown", "RB", "CIN", 18.0),
    ("De'Von Achane", "RB", "MIA", 16.0), ("Omarion Hampton", "RB", "LAC", 14.7),
    ("AJ Brown", "WR", "NE", 21.3), ("Brock Bowers", "TE", "LV", 20.0),
    ("Trey McBride", "TE", "ARI", 23.0), ("George Pickens", "WR", "DAL", 24.0),
    ("Nico Collins", "WR", "HOU", 21.7), ("Rashee Rice", "WR", "KC", 27.7),
    ("Josh Allen", "QB", "BUF", 27.7), ("Colston Loveland", "TE", "CHI", 42.7),
    ("Lamar Jackson", "QB", "BAL", 49.7), ("Jayden Daniels", "QB", "WAS", 64.7),
    ("Tyler Warren", "TE", "IND", 56.0), ("Joe Burrow", "QB", "CIN", 60.7),
]

# Filler shape: enough bodies per position to complete a 12-team, 16-round draft.
FILLER = [("WR", 70), ("RB", 55), ("TE", 25), ("QB", 20), ("DEF", 20), ("K", 20)]


def build(path: str) -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Full Ledger"
    sheet.append(HEADERS)

    pos_counts: dict[str, int] = {}
    rank = 0

    for name, position, team, adp in REAL_TOP:
        rank += 1
        pos_counts[position] = pos_counts.get(position, 0) + 1
        sheet.append([
            rank, name, position, team, f"{position}{pos_counts[position]:02d}",
            adp, round(adp - rank, 1), f"{position}{pos_counts[position]:02d}", 0,
        ])

    for position, count in FILLER:
        for _ in range(count):
            rank += 1
            pos_counts[position] = pos_counts.get(position, 0) + 1
            adp = float(rank) + ((rank % 7) - 3)
            sheet.append([
                rank, f"Sample {position}{pos_counts[position]}", position, "FA",
                f"{position}{pos_counts[position]:02d}", adp, round(adp - rank, 1),
                f"{position}{pos_counts[position]:02d}", 0,
            ])

    workbook.save(path)
    print(f"wrote {path}: {rank} players")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "data/sample_rankings.xlsx")
