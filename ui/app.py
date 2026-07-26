"""Live draft assistant.

Run with:
    uv run streamlit run ui/app.py

Built for the in-person league, where every pick is typed in by hand while a
clock runs, so the design priorities are: one keystroke path for the common
case, no accidental data loss, and never a blank screen waiting on a network
call. The board and projections are computed once and cached; the draft state
is written to disk after every pick so a crash costs nothing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import load_league_settings  # noqa: E402
from data.ingest_etr import load_etr_rankings  # noqa: E402
from data.models import Player, Position  # noqa: E402
from data.name_matching import match_players, resolve_keepers  # noqa: E402
from engine.draft_state import DraftState  # noqa: E402
from engine.recommend import recommend, roster_gaps  # noqa: E402
from scripts.build_board import build_board  # noqa: E402

LEAGUE_DIR = Path(__file__).resolve().parent.parent / "config" / "leagues"
STATE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"

POSITION_COLORS = {
    "RB": "#C6E0B4", "WR": "#BDD7EE", "TE": "#FFE699",
    "QB": "#F4B7B7", "K": "#D9D2E9", "DEF": "#D9D9D9",
}


@st.cache_data(show_spinner="Building board (fitting projection curves)...")
def load_board(league_path: str, etr_path: str) -> list[dict]:
    return build_board(league_path, etr_path)


@st.cache_data(show_spinner=False)
def load_players(etr_path: str) -> list[Player]:
    players, _ = load_etr_rankings(etr_path)
    return players


def state_path(league_name: str) -> Path:
    slug = league_name.lower().replace(" ", "_")
    return STATE_DIR / f"draft_state_{slug}.json"


def get_draft_state(league) -> DraftState:
    """DraftState for this league, restored from disk if a draft is in progress."""
    key = f"draft_state::{league.name}"
    if key not in st.session_state:
        path = state_path(league.name)
        if path.exists():
            st.session_state[key] = DraftState.load(path, league)
        else:
            st.session_state[key] = DraftState(league=league)
    return st.session_state[key]


def persist(state: DraftState, league) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state.save(state_path(league.name))


def position_badge(position: str) -> str:
    color = POSITION_COLORS.get(position, "#EEEEEE")
    return (
        f"<span style='background:{color};color:#111;padding:2px 8px;"
        f"border-radius:4px;font-weight:600;font-size:0.85em'>{position}</span>"
    )


def main() -> None:
    st.set_page_config(page_title="Draft Assistant", layout="wide")

    with st.sidebar:
        st.header("Setup")
        league_files = sorted(p.name for p in LEAGUE_DIR.glob("*.yaml"))
        league_file = st.selectbox("League", league_files)
        league_path = str(LEAGUE_DIR / league_file)
        league = load_league_settings(league_path)

        etr_path = st.text_input(
            "ETR export path",
            help="Path to the ETR .xlsx or .csv rankings export.",
        )

        # Draft slot is usually not known until draft day, so it is set here
        # rather than baked into the league config file.
        league.draft_slot = st.number_input(
            "Your draft slot",
            min_value=1,
            max_value=league.num_teams,
            value=league.draft_slot,
        )

        st.caption(
            f"{league.num_teams} teams | {league.rounds} rounds | "
            f"{len(league.keepers)} keepers"
        )

    if not etr_path or not Path(etr_path).exists():
        st.info("Enter the path to your ETR export in the sidebar to begin.")
        st.stop()

    board = load_board(league_path, etr_path)
    all_players = load_players(etr_path)
    state = get_draft_state(league)

    board_by_id = {row["player_id"]: row for row in board}
    kept_ids = set(resolve_keepers(league.keepers, all_players).values())
    draftable = [
        p for p in all_players
        if p.player_id in board_by_id and p.player_id not in kept_ids
    ]
    available = [p for p in draftable if not state.is_drafted(p.player_id)]

    # --- Status bar -------------------------------------------------------
    on_clock = state.on_the_clock_team_index
    my_turn = on_clock == state.my_team_index
    turns = state.picks_until_my_turn(2)

    cols = st.columns([1.2, 1, 1, 1, 1])
    cols[0].metric("Pick", f"{min(state.next_overall_pick, state.total_picks)} / {state.total_picks}")
    cols[1].metric("Round", state.current_round or "—")
    cols[2].metric(
        "On the clock",
        "YOU" if my_turn else (f"Team {on_clock + 1}" if on_clock is not None else "—"),
    )
    cols[3].metric("Picks until you", turns[0] if turns else "—")
    cols[4].metric("Your picks left", state.my_remaining_picks())

    if state.is_complete:
        st.success("Draft complete.")
    elif my_turn:
        st.success("**You're on the clock.**")

    st.divider()
    left, right = st.columns([1, 1.15])

    # --- Pick entry -------------------------------------------------------
    with left:
        st.subheader("Record a pick")

        with st.form("pick_entry", clear_on_submit=True):
            query = st.text_input(
                "Player",
                placeholder="Type a name, then Enter",
                label_visibility="collapsed",
            )
            submitted = st.form_submit_button("Record pick", type="primary")

        if submitted and query.strip():
            matches = match_players(query, available, limit=5)
            if not matches:
                st.error(f"No available player matches {query!r}.")
            elif len(matches) == 1 or matches[0][1] - matches[1][1] >= 15:
                player = matches[0][0]
                state.record_pick(player.player_id)
                persist(state, league)
                st.rerun()
            else:
                st.warning(f"{query!r} is ambiguous — pick one:")
                st.session_state["pending_matches"] = [p.player_id for p, _ in matches]

        pending = st.session_state.get("pending_matches")
        if pending:
            for player_id in pending:
                row = board_by_id.get(player_id)
                if row is None:
                    continue
                if st.button(
                    f"{row['name']} ({row['position']} · {row['team']})", key=f"pick_{player_id}"
                ):
                    state.record_pick(player_id)
                    persist(state, league)
                    st.session_state.pop("pending_matches", None)
                    st.rerun()

        if st.button("Undo last pick", disabled=not state.pick_history):
            state.undo_last_pick()
            persist(state, league)
            st.rerun()

        # Recent picks give a quick visual check that entry kept up with the room.
        if state.pick_history:
            st.caption("Recent picks")
            for pick in reversed(state.pick_history[-8:]):
                row = board_by_id.get(pick.player_id, {})
                who = "you" if pick.team_index == state.my_team_index else f"team {pick.team_index + 1}"
                st.markdown(
                    f"`{pick.overall_pick:>3}` {position_badge(row.get('position', '?'))} "
                    f"**{row.get('name', pick.player_id)}** — {who}",
                    unsafe_allow_html=True,
                )

        st.divider()
        st.subheader("Your roster")
        unfilled, flex_needed = roster_gaps(
            state, league, {r["player_id"]: Position(r["position"]) for r in board}
        )
        my_ids = state.roster_player_ids(state.my_team_index)
        if my_ids:
            for player_id in my_ids:
                row = board_by_id.get(player_id, {})
                st.markdown(
                    f"{position_badge(row.get('position', '?'))} {row.get('name', player_id)}",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No picks yet.")

        gaps = [f"{count} {pos.value}" for pos, count in unfilled.items() if count]
        if flex_needed:
            gaps.append(f"{flex_needed} FLEX")
        st.caption("Still need: " + (", ".join(gaps) if gaps else "starters full"))

    # --- Recommendations --------------------------------------------------
    with right:
        st.subheader("Best available")
        recs = recommend(state, board, league, top_n=12)
        if not recs:
            st.caption("No players available.")
        for rec in recs:
            edge = f" · ADP {rec.adp:.0f}" if rec.adp is not None else ""
            st.markdown(
                f"{position_badge(rec.position)} **{rec.name}** "
                f"<span style='color:#888'>{rec.team or ''}{edge} · "
                f"tier {rec.tier} · VORP {rec.vorp:.0f}</span>",
                unsafe_allow_html=True,
            )
            if rec.reasons:
                st.caption(" · ".join(rec.reasons))


if __name__ == "__main__":
    main()
