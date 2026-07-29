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


def write_rosters(path: Path, mine=None, rivals=None) -> Path:
    """A roster workbook with arbitrary contents, for post-deadline imports."""
    workbook = Workbook()
    sheet = workbook.active
    blocks = [("Andrew's Team - Andrew", mine if mine is not None else MY_ROSTER[:2]),
              ("Rivals - Someone", rivals if rivals is not None else RIVAL_ROSTER)]
    for index, (header, rows) in enumerate(blocks):
        col = 1 + index * 5
        sheet.cell(row=1, column=col, value=header)
        for offset, label in enumerate(("Player", "2025 Pts", "Bye", "Salary")):
            sheet.cell(row=2, column=col + offset, value=label)
        for r, (player, salary) in enumerate(rows, start=3):
            sheet.cell(row=r, column=col, value=player)
            sheet.cell(row=r, column=col + 3, value=salary)
        sheet.cell(row=3 + len(rows), column=col, value=f"{len(rows)} Total Players")
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


# -- live auction -----------------------------------------------------------

def test_auction_page_renders(client):
    response = client.get("/auction")
    assert response.status_code == 200
    body = html.unescape(response.text)
    assert "Live Auction" in body
    assert "Max bid" in body
    assert "Inflation" in body


def test_auction_opens_from_the_post_deadline_state(session):
    """Your keep decisions are the auction's opening roster, not a fresh slate."""
    session.apply_recommendation()
    auction = session.start_auction()
    kept = session.kept_contracts()

    me = auction.status(session.my_team)
    assert me.filled == len(kept)
    assert me.budget == session.rules.salary_cap - sum(c.salary for c in kept)
    assert auction.inflation() == pytest.approx(1.0)


def test_kept_players_are_not_on_the_auction_board(session):
    session.apply_recommendation()
    auction = session.start_auction()
    kept_ids = {session.key(c) for c in session.kept_contracts()}
    assert not kept_ids & {p.player_id for p in auction.available()}


def test_recording_a_sale_through_the_route(client, session):
    client.get("/auction")
    response = client.post(
        "/auction/sale", data={"player": "Spare Wideout", "price": "20", "team": "Andrew's Team"}
    )
    assert response.status_code == 200
    assert "Spare Wideout" in html.unescape(response.text)


def test_a_partial_name_resolves(client):
    client.get("/auction")
    response = client.post(
        "/auction/sale", data={"player": "spare arm", "price": "3", "team": "Rivals"}
    )
    assert "Spare Arm" in response.text
    assert "No clear match" not in response.text


def test_an_unresolvable_name_asks_rather_than_guessing(client):
    """Recording the wrong player mid-auction costs more than a second question."""
    client.get("/auction")
    response = client.post(
        "/auction/sale", data={"player": "zzzz nobody", "price": "5", "team": "Rivals"}
    )
    assert response.status_code == 200
    assert "No clear match" in html.unescape(response.text)


def test_undo_reverses_the_last_sale(client):
    client.get("/auction")
    client.post("/auction/sale", data={"player": "Spare Wideout", "price": "20", "team": "Rivals"})
    response = client.post("/auction/undo")
    assert "Undid Spare Wideout" in html.unescape(response.text)


def test_undo_with_nothing_to_undo_is_reported_not_crashed(client):
    client.get("/auction")
    assert "Nothing to undo" in client.post("/auction/undo").text


def test_a_bad_price_is_reported_on_the_board(client):
    client.get("/auction")
    response = client.post(
        "/auction/sale", data={"player": "Spare Wideout", "price": "0", "team": "Rivals"}
    )
    assert "minimum bid" in html.unescape(response.text)


def test_sales_are_persisted_when_a_store_is_attached(session, tmp_path):
    from app.store import AuctionStore

    store = AuctionStore(tmp_path / "auction.db")
    client = TestClient(create_app(session, store))
    client.get("/auction")
    client.post("/auction/sale", data={"player": "Spare Wideout", "price": "20", "team": "Rivals"})

    assert [s.player_name for s in store.load()] == ["Spare Wideout"]
    client.post("/auction/undo")
    assert store.load() == []


def test_a_near_miss_never_auto_commits(client):
    """A loose single match must not be recorded silently.

    "Rival Star" is already rostered, so he is not on the board -- but he
    shares a token with "Rival Filler", who is. `resolve_one`'s margin rule is
    satisfied by one weak candidate in a thin field, so the auction path needs
    an absolute score bar as well. Getting this wrong files a sale against the
    wrong player, which at a live auction is both costly and easy to miss.
    """
    client.get("/auction")
    response = client.post(
        "/auction/sale", data={"player": "Rival Star", "price": "20", "team": "Rivals"}
    )
    body = html.unescape(response.text)
    assert "No clear match" in body
    assert "Undid" not in body


def test_changing_the_cut_plan_reopens_the_auction(client, session):
    """Whichever request opened this page first must not freeze the rosters."""
    client.get("/auction")
    before = html.unescape(client.get("/auction").text)

    session.apply_recommendation()
    after = html.unescape(client.get("/auction").text)

    assert before != after
    assert "Opening rosters are locked" not in after


def test_the_opening_state_freezes_once_lots_have_sold(client, session):
    """Rebuilding would strand the sale log against rosters it never saw."""
    client.get("/auction")
    client.post("/auction/sale", data={"player": "Spare Arm", "price": "4", "team": "Rivals"})

    session.apply_recommendation()
    body = html.unescape(client.get("/auction").text)

    assert "Opening rosters are locked" in body
    assert "Spare Arm" in body  # the sale log survives


# -- post-deadline import ---------------------------------------------------

def test_importing_real_rosters_replaces_projections(session, tmp_path):
    """After 17 Aug a rival's roster is a fact, and a fact beats a guess."""
    projected = session.start_auction().status("Rivals")
    # The optimizer projects Rivals cutting Filler, who is priced well under his
    # $30 salary. Suppose they keep him anyway -- owners do.
    final = write_rosters(
        tmp_path / "final.xlsx",
        rivals=[("Star, Rival KC RB", 12), ("Filler, Rival GB TE", 30)],
    )
    session.adopt_post_deadline_rosters(final)
    actual = session.start_auction().status("Rivals")

    assert session.post_deadline_source == str(final)
    assert projected.filled == 1  # the guess
    assert actual.filled == 2  # the fact
    assert actual.budget == session.rules.salary_cap - 42 < projected.budget


def test_importing_clears_your_own_pending_decisions(session, tmp_path):
    """The new workbook already reflects your drops; re-applying would double-count."""
    session.apply_recommendation()
    assert session.cut

    session.adopt_post_deadline_rosters(write_rosters(tmp_path / "final.xlsx"))
    assert session.cut == set()
    assert session.tagged == set()


def test_post_deadline_start_uses_every_teams_actual_roster(session, tmp_path):
    session.adopt_post_deadline_rosters(write_rosters(tmp_path / "final.xlsx"))
    auction = session.start_auction()

    for roster in session.rosters:
        status = auction.status(roster.name)
        assert status.filled == len(roster.contracts)
        assert status.budget == session.rules.salary_cap - roster.salary


def test_compliance_problems_are_reported_not_raised(session, tmp_path):
    """An over-cap roster after the deadline means stale data, not a reason to refuse."""
    over = write_rosters(
        tmp_path / "over.xlsx",
        mine=[("Back, Bargain PHI RB", 90), ("Value, Fair DAL WR", 90)],
    )
    issues = session.adopt_post_deadline_rosters(over)

    assert any("Andrew's Team" in issue and "over the cap" in issue for issue in issues)
    assert session.start_auction().status("Andrew's Team").budget == -80


def test_a_workbook_missing_your_team_is_rejected(session, tmp_path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.cell(row=1, column=1, value="Someone Else - Nobody")
    for offset, label in enumerate(("Player", "2025 Pts", "Bye", "Salary")):
        sheet.cell(row=2, column=1 + offset, value=label)
    sheet.cell(row=3, column=1, value="Star, Rival KC RB")
    sheet.cell(row=3, column=4, value=5)
    path = tmp_path / "wrong.xlsx"
    workbook.save(path)

    with pytest.raises(ValueError, match="no team named"):
        session.adopt_post_deadline_rosters(path)


def test_the_auction_page_says_whether_rivals_are_real(client, session, tmp_path):
    assert "projections, not facts" in html.unescape(client.get("/auction").text)

    session.adopt_post_deadline_rosters(write_rosters(tmp_path / "final.xlsx"))
    assert "projections, not facts" not in html.unescape(client.get("/auction").text)


# -- paper fallback ---------------------------------------------------------

def test_paper_board_renders_the_essentials(session):
    from scripts.fallback_board import render

    page = html.unescape(render(session, rows=10))

    assert "Max bid by budget and slots left".upper() in page.upper()
    assert "Opting out is permanent" in page  # 5.7.2, the rule that costs you money
    assert "PROJECTED, not final" in page  # provenance when rivals are guesses
    assert page.count("<tr>") > 10
    assert "Sold for" in page and "class='write'" in page  # blanks to write into


def test_paper_board_states_when_rosters_are_real(session, tmp_path):
    from scripts.fallback_board import render

    session.adopt_post_deadline_rosters(write_rosters(tmp_path / "final.xlsx"))
    page = render(session, rows=5)

    assert "PROJECTED, not final" not in page
    assert "post-deadline rosters from final.xlsx" in page
