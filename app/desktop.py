"""Launch the assistant in a native desktop window.

The server runs on loopback in a background thread and pywebview wraps it in a
real window, so this ships as a `.app`/`.exe` rather than as "open your browser
and go to localhost". That matters for 24 August: the draft is in person, in
somebody's house, at 8pm, and the tool has to start like an application.

    uv run python -m app.desktop rosters.xlsx etr_auction_values.csv

`--no-window` runs the server alone, which is how to work on it over SSH or in
any environment without a GUI toolkit.
"""
from __future__ import annotations

import argparse
import socket
import threading
from pathlib import Path

import uvicorn

from app.server import create_app
from app.session import Session

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LEAGUE = ROOT / "config" / "leagues" / "ffl_ny.yaml"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roster", type=Path, help="preseason roster & salary workbook")
    parser.add_argument("etr", type=Path, help="ETR auction values export (.csv or .xlsx)")
    parser.add_argument("--league", type=Path, default=DEFAULT_LEAGUE)
    parser.add_argument("--team", default="Andrew's Team")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--value-column", default="half_ppr")
    parser.add_argument("--tags", type=int, default=1, help="franchise tags held this year")
    parser.add_argument("--no-window", action="store_true", help="serve without a GUI window")
    parser.add_argument("--port", type=int, default=0)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    session = Session.load(
        args.league, args.roster, args.etr,
        my_team=args.team, season=args.season, value_column=args.value_column,
    )
    session.tags_available = args.tags
    app = create_app(session)
    port = args.port or _free_port()

    if args.no_window:
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
        return

    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    threading.Thread(target=server.run, daemon=True).start()

    import webview  # imported late so the server path works with no GUI toolkit present

    webview.create_window(
        f"{session.league.name} — {session.my_team}",
        f"http://127.0.0.1:{port}",
        width=1180, height=900,
    )
    webview.start()


if __name__ == "__main__":
    main()
