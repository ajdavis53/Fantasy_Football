"""Parsing the commissioner's preseason roster workbook.

The fixture is generated rather than committed so the layout being tested --
side-by-side team blocks, packed player cells, non-breaking spaces -- is
visible in the test rather than hidden in a binary.
"""
from __future__ import annotations

import pytest
from openpyxl import Workbook

from data.ingest_roster import (
    RosterIngestError,
    contract_player_id,
    load_roster_workbook,
    parse_player_cell,
)
from data.models import Position

NBSP = "\xa0"


def write_workbook(path, blocks, *, gap: int = 1):
    """Lay teams out in side-by-side blocks, as the commissioner's sheet does."""
    workbook = Workbook()
    sheet = workbook.active
    for index, (header, rows) in enumerate(blocks):
        col = 1 + index * (4 + gap)
        sheet.cell(row=1, column=col, value=header)
        for offset, label in enumerate(("Player", "2025 Pts", "Bye", "Salary")):
            sheet.cell(row=2, column=col + offset, value=label)
        for r, row in enumerate(rows, start=3):
            for offset, value in enumerate(row):
                sheet.cell(row=r, column=col + offset, value=value)
        last = 3 + len(rows)
        sheet.cell(row=last, column=col, value=f"{len(rows)} Total Players")
        sheet.cell(row=last + 1, column=col, value="Total:")
        sheet.cell(row=last + 2, column=col, value="Salary Cap:")
    workbook.save(path)
    return path


@pytest.fixture
def workbook(tmp_path):
    return write_workbook(
        tmp_path / "rosters.xlsx",
        [
            (
                f"Andrew's Team{NBSP}- Andrew Davis",
                [
                    (f"Prescott, Dak DAL QB{NBSP}(Q)", 313.78, 14, 17),
                    ("Barkley, Saquon PHI RB", 213.8, 10, 86),
                    ("Hunt, Kareem FA RB", 136.4, "-", 15),
                    ("Cowboys, Dallas DAL Def", 31, 14, 8),
                ],
            ),
            (
                f"Tire Fire Sale{NBSP}- RJ Kalb",
                [
                    ("McBride, Trey ARI TE", 252.9, 14, 14),
                    ("Walker III, Kenneth KCC RB", 176.4, 5, 47),
                    ("Egbuka, Emeka TBB WR", 164.2, 10, 20),
                ],
            ),
        ],
    )


def test_reads_every_team_block(workbook):
    teams = load_roster_workbook(workbook)
    assert [t.team for t in teams] == ["Andrew's Team", "Tire Fire Sale"]
    assert [t.owner for t in teams] == ["Andrew Davis", "RJ Kalb"]


def test_reads_salaries_and_totals(workbook):
    andrew, rj = load_roster_workbook(workbook)
    assert andrew.salary == 17 + 86 + 15 + 8
    assert rj.salary == 14 + 47 + 20
    assert len(andrew.contracts) == 4


def test_stops_at_the_totals_rows(workbook):
    """`4 Total Players` and the cap rows must not be parsed as players."""
    andrew, _ = load_roster_workbook(workbook)
    assert all("Total" not in c.player_name for c in andrew.contracts)


def test_flips_surname_first_names(workbook):
    andrew, _ = load_roster_workbook(workbook)
    assert [c.player_name for c in andrew.contracts][:2] == ["Dak Prescott", "Saquon Barkley"]


def test_defences_parse_as_def_with_a_natural_name(workbook):
    andrew, _ = load_roster_workbook(workbook)
    defense = andrew.contracts[-1]
    assert defense.player_name == "Dallas Cowboys"
    assert defense.position is Position.DEF


def test_normalizes_nfl_team_codes_to_match_rankings(workbook):
    """The workbook writes KCC/TBB/ARZ; the rankings write KC/TB/ARI."""
    _, rj = load_roster_workbook(workbook)
    assert {c.nfl_team for c in rj.contracts} == {"ARI", "KC", "TB"}


def test_contracts_key_on_the_same_player_id_as_rankings(workbook):
    _, rj = load_roster_workbook(workbook)
    walker = next(c for c in rj.contracts if c.player_name.startswith("Kenneth"))
    assert contract_player_id(walker) == "kenneth-walker-iii-kc-rb"


def test_captures_bye_weeks_and_prior_points(workbook):
    andrew, _ = load_roster_workbook(workbook)
    dak = contract_player_id(andrew.contracts[0])
    assert andrew.bye_weeks[dak] == 14
    assert andrew.prior_points[dak] == pytest.approx(313.78)


def test_tolerates_a_missing_bye_week(workbook):
    """Free agents have no bye; the workbook writes '-'."""
    andrew, _ = load_roster_workbook(workbook)
    hunt = contract_player_id(andrew.contracts[2])
    assert hunt not in andrew.bye_weeks
    assert andrew.prior_points[hunt] == pytest.approx(136.4)


def test_block_detection_survives_a_different_column_gap(tmp_path):
    path = write_workbook(
        tmp_path / "wide.xlsx",
        [("A{}- x".format(NBSP), [("Barkley, Saquon PHI RB", 1, 10, 5)]),
         ("B{}- y".format(NBSP), [("McBride, Trey ARI TE", 1, 14, 5)])],
        gap=3,
    )
    assert [t.team for t in load_roster_workbook(path)] == ["A", "B"]


def test_a_workbook_without_team_blocks_is_an_error(tmp_path):
    workbook = Workbook()
    workbook.active["A1"] = "not a roster"
    workbook.save(tmp_path / "empty.xlsx")
    with pytest.raises(RosterIngestError, match="no team blocks"):
        load_roster_workbook(tmp_path / "empty.xlsx")


def test_an_unreadable_salary_names_the_player(tmp_path):
    path = write_workbook(
        tmp_path / "bad.xlsx",
        [(f"A{NBSP}- x", [("Barkley, Saquon PHI RB", 1, 10, "n/a")])],
    )
    with pytest.raises(RosterIngestError, match="Saquon Barkley"):
        load_roster_workbook(path)


@pytest.mark.parametrize(
    "cell,expected",
    [
        ("Prescott, Dak DAL QB", ("Dak Prescott", "DAL", Position.QB)),
        (f"Harrison Jr., Marvin ARI WR{NBSP}(Q)", ("Marvin Harrison Jr.", "ARI", Position.WR)),
        ("St. Brown, Amon-Ra DET WR", ("Amon-Ra St. Brown", "DET", Position.WR)),
        ("Thomas Jr., Brian JAC WR", ("Brian Thomas Jr.", "JAX", Position.WR)),
        ("Bills, Buffalo BUF Def", ("Buffalo Bills", "BUF", Position.DEF)),
    ],
)
def test_parse_player_cell(cell, expected):
    assert parse_player_cell(cell.replace(NBSP, " ")) == expected


def test_parse_player_cell_rejects_non_player_rows():
    assert parse_player_cell("14 Total Players") is None
    assert parse_player_cell("Salary Cap:") is None


def test_links_contracts_to_ranked_players():
    from data.ingest_roster import link_contracts_to_players
    from data.models import Contract, Player

    def player(name, team, position):
        return Player(
            player_id=f"{name.lower().replace(' ', '-')}-{team.lower()}-{position.value.lower()}",
            name=name, nfl_team=team, position=position,
            eligible_positions=frozenset({position}),
        )

    players = [
        player("Saquon Barkley", "PHI", Position.RB),
        player("Trey McBride", "ARI", Position.TE),
        player("DAL DST", "DAL", Position.DEF),
    ]
    contracts = [
        Contract(player_name="Saquon Barkley", salary=86, position=Position.RB, nfl_team="PHI"),
        # traded since the rankings were published: same player, different team
        Contract(player_name="Trey McBride", salary=14, position=Position.TE, nfl_team="SEA"),
        # the two sources name defenses irreconcilably
        Contract(player_name="Dallas Cowboys", salary=8, position=Position.DEF, nfl_team="DAL"),
        Contract(player_name="Nobody At All", salary=1, position=Position.WR, nfl_team="NYJ"),
    ]
    mapping, unmatched = link_contracts_to_players(contracts, players)

    assert mapping[contract_player_id(contracts[0])] == "saquon-barkley-phi-rb"
    assert mapping[contract_player_id(contracts[1])] == "trey-mcbride-ari-te"
    assert mapping[contract_player_id(contracts[2])] == "dal-dst-dal-def"
    assert [c.player_name for c in unmatched] == ["Nobody At All"]
