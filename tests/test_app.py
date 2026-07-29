"""Session state and the routes over it.

Fixtures are generated rather than committed so the shapes being tested -- the
workbook's block layout, the rankings export's columns -- stay visible.
"""
from __future__ import annotations

import csv
import html
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.server import create_app
from app.session import Session
from engine.cuts import RetentionPolicy

FIXTURES = Path(__file__).parent / "fixtures"
LEAGUE = FIXTURES / "test_auction_league.yaml"

# name, pos, nfl team, published auction value ($100 across 2 teams x $50)
POOL = [
    ("Bargain Back", "RB", "PHI", 30),
    ("Fair Value", "WR", "DAL", 20),
    ("Overpaid Man", "WR", "SF", 8),
    ("Rival Star", "RB", "KC", 26),
    ("Rival Filler", "TE", "GB", 4),
    ("Spare Arm", "QB", "BUF", 6),
    ("Spare Wideout", "WR", "NYJ", 5),
    ("DAL DST", "DST", "DAL", 1),
]

# player, salary -- Bargain Back is the only contract worth its money
MY_ROSTER = [("Back, Bargain PHI RB", 18), ("Value, Fair DAL WR", 20),
             ("Man, Overpaid SF WR", 40), ("Cowboys, Dallas DAL Def", 8)]
RIVAL_ROSTER = [("Star, Rival KC RB", 12), ("Filler, Rival GB TE", 30)]


@pytest.fixture
def etr_csv(tmp_path) -> Path:
    path = tmp_path / "etr.csv"
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Player", "Position", "Team", "ETR Half PPR"])
        for name, position, team, value in POOL:
            writer.writerow([name, position, team, value])
    return path


@pytest.fixture
def roster_xlsx(tmp_path) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    for index, (header, rows) in enumerate(
        [("Andrew's Team - Andrew", MY_ROSTER), ("Rivals - Someone", RIVAL_ROSTER)]
    ):
        col = 1 + index * 5
        sheet.cell(row=1, column=col, value=header)
        for offset, label in enumerate(("Player", "2025 Pts", "Bye", "Salary")):
            sheet.cell(row=2, column=col + offset, value=label)
        for r, (player, salary) in enumerate(rows, start=3):
            sheet.cell(row=r, column=col, value=player)
            sheet.cell(row=r, column=col + 1, value=100)
            sheet.cell(row=r, column=col + 2, value=9)
            sheet.cell(row=r, column=col + 3, value=salary)
        sheet.cell(row=3 + len(rows), column=col, value=f"{len(rows)} Total Players")
    path = tmp_path / "rosters.xlsx"
    workbook.save(path)
    return path


@pytest.fixture
def session(roster_xlsx, etr_csv) -> Session:
    return Session.load(LEAGUE, roster_xlsx, etr_csv, my_team="Andrew's Team", season=2026)


@pytest.fixture
def client(session) -> TestClient:
    return TestClient(create_app(session))


# -- session ----------------------------------------------------------------

def test_loads_both_rosters_and_finds_mine(session):
    assert {r.name for r in session.rosters} == {"Andrew's Team", "Rivals"}
    assert len(session.my_roster.contracts) == 4


def test_unknown_team_name_is_a_clear_error(roster_xlsx, etr_csv):
    with pytest.raises(ValueError, match="no team named 'Nobody'"):
        Session.load(LEAGUE, roster_xlsx, etr_csv, my_team="Nobody")


def test_summary_reflects_the_roster_as_it_stands(session):
    summary = session.summary()
    assert summary["kept"] == 4
    assert summary["salary"] == 18 + 20 + 40 + 8
    assert summary["over_cap"] is False
    assert summary["budget"] == 100 - 86


def test_cutting_frees_budget_and_a_slot(session):
    before = session.summary()
    overpaid = next(r for r in session.my_rows() if r["name"] == "Overpaid Man")
    session.toggle_cut(overpaid["id"])
    after = session.summary()

    assert after["kept"] == before["kept"] - 1
    assert after["budget"] == before["budget"] + 40
    assert after["slots"] == before["slots"] + 1


def test_max_bid_reserves_a_dollar_for_every_remaining_slot(session):
    session.cut = {row["id"] for row in session.my_rows()}
    summary = session.summary()
    assert summary["slots"] == session.rules.max_roster
    assert summary["max_bid"] == 100 - (session.rules.max_roster - 1)


def test_tagging_discounts_the_salary(session):
    bargain = next(r for r in session.my_rows() if r["name"] == "Bargain Back")
    assert session.toggle_tag(bargain["id"]) is True

    tagged = next(r for r in session.my_rows() if r["name"] == "Bargain Back")
    assert tagged["salary"] == 18 - session.rules.franchise_discount
    assert tagged["base_salary"] == 18
    assert tagged["tagged"] is True


def test_cannot_spend_more_tags_than_are_held(session):
    rows = session.my_rows()
    assert session.toggle_tag(rows[0]["id"]) is True
    assert session.toggle_tag(rows[1]["id"]) is False  # only one tag held
    assert len(session.tagged) == 1


def test_tagging_a_cut_player_restores_him(session):
    bargain = next(r for r in session.my_rows() if r["name"] == "Bargain Back")
    session.toggle_cut(bargain["id"])
    session.toggle_tag(bargain["id"])
    assert bargain["id"] not in session.cut


def test_my_decisions_move_the_market(session):
    """Releasing contracts adds money and players to the auction, changing prices."""
    before = session.market.dollars
    session.cut = {row["id"] for row in session.my_rows()}
    assert session.market.dollars > before


def test_switching_scenario_changes_the_price_level(session):
    session.policy = RetentionPolicy.MINIMUM_COMPLIANCE
    lean = session.market.dollars
    session.policy = RetentionPolicy.SURPLUS_MAXIMIZING
    assert session.market.dollars > lean


def test_recommendation_is_independent_of_current_decisions(session):
    """It advises on the decisions, so it must not be conditioned on them."""
    before = {c.player_name for c in session.recommendation().keep}
    session.cut = {row["id"] for row in session.my_rows()}
    assert {c.player_name for c in session.recommendation().keep} == before


def test_apply_recommendation_then_reset(session):
    session.apply_recommendation()
    kept = {row["name"] for row in session.my_rows() if row["kept"]}
    assert kept == {c.player_name for c in session.recommendation().keep}

    session.reset()
    assert all(row["kept"] for row in session.my_rows())
    assert session.tagged == set()


def test_league_table_flags_who_must_sell(session):
    rows = {row["team"]: row for row in session.league_table()}
    assert rows["Andrew's Team"]["is_mine"] is True
    assert rows["Rivals"]["committed"] == 42
    assert all(row["must_cut"] >= 0 for row in rows.values())


def test_scenarios_report_both_brackets(session):
    scenarios = session.scenarios()
    assert {s["policy"] for s in scenarios} == {p.value for p in RetentionPolicy}
    assert sum(1 for s in scenarios if s["active"]) == 1


def test_solves_are_cached(session):
    first = session.equilibrium()
    assert session.equilibrium() is first
    session.toggle_cut(session.my_rows()[0]["id"])
    assert session.equilibrium() is not first


# -- routes -----------------------------------------------------------------

def test_index_renders_the_board(client):
    response = client.get("/")
    assert response.status_code == 200
    # unescaped, because Jinja renders the apostrophe in "Andrew's" as &#39;
    body = html.unescape(response.text)
    assert "Andrew's Team" in body
    assert "Bargain Back" in body
    assert "Max single bid" in body


def test_toggle_returns_the_updated_board(client, session):
    row = next(r for r in session.my_rows() if r["name"] == "Overpaid Man")
    response = client.post(f"/toggle/{row['id']}")

    assert response.status_code == 200
    assert "<html" not in response.text  # a fragment, not a whole page
    assert next(r for r in session.my_rows() if r["name"] == "Overpaid Man")["kept"] is False


def test_tag_route_applies_the_discount(client, session):
    row = next(r for r in session.my_rows() if r["name"] == "Bargain Back")
    assert client.post(f"/tag/{row['id']}").status_code == 200
    assert session.tagged == {row["id"]}


def test_scenario_route_switches_policy(client, session):
    response = client.post("/scenario", data={"policy": "minimum_compliance"})
    assert response.status_code == 200
    assert session.policy is RetentionPolicy.MINIMUM_COMPLIANCE


def test_apply_and_reset_routes(client, session):
    assert client.post("/apply").status_code == 200
    assert session.cut  # the roster is mostly bad, so something was dropped
    assert client.post("/reset").status_code == 200
    assert session.cut == set()


def test_unknown_player_id_does_not_crash_the_board(client):
    """Ids come from the rendered page, but a stale fragment must not 500."""
    assert client.post("/toggle/no-such-player").status_code == 200
