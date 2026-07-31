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
import importlib
import socket
import sys
import threading
from pathlib import Path

import uvicorn

from app.server import create_app
from app.session import Session
from app.store import AuctionStore

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LEAGUE = ROOT / "config" / "leagues" / "ffl_ny.yaml"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def check_environment(args) -> list[tuple[bool, str]]:
    """Verify everything draft night depends on, so failures surface early.

    Every line here is something that has actually gone wrong or plausibly
    could: a missing GUI backend, an unreadable workbook, a port already taken,
    a sale log on a read-only path. Discovering any of them at 8pm on the 24th
    is expensive; discovering them now costs nothing.
    """
    results: list[tuple[bool, str]] = []

    results.append((sys.version_info >= (3, 11),
                    f"python {sys.version_info.major}.{sys.version_info.minor} (need 3.11+)"))

    for module in ("fastapi", "uvicorn", "jinja2", "openpyxl", "rapidfuzz"):
        try:
            importlib.import_module(module)
            results.append((True, f"{module} importable"))
        except Exception as exc:
            results.append((False, f"{module} missing -- run `uv sync` ({exc})"))

    # The GUI backend is the one thing that cannot be checked without trying.
    try:
        import webview  # noqa: F401
        try:
            webview.guilib.initialize()
            results.append((True, "pywebview has a working GUI backend"))
        except Exception as exc:
            results.append((False, f"pywebview found no GUI backend -- use --no-window ({exc})"))
    except Exception as exc:
        results.append((False, f"pywebview not importable -- use --no-window ({exc})"))

    for label, path in (("roster workbook", args.roster), ("ETR export", args.etr),
                        ("league config", args.league)):
        results.append((path.exists(), f"{label}: {path}"))

    if args.post_deadline:
        results.append((args.post_deadline.exists(),
                        f"post-deadline workbook: {args.post_deadline}"))

    try:
        args.db.parent.mkdir(parents=True, exist_ok=True)
        probe = args.db.parent / ".write-probe"
        probe.write_text("")
        probe.unlink()
        results.append((True, f"sale log is writable: {args.db}"))
    except Exception as exc:
        results.append((False, f"cannot write the sale log at {args.db} ({exc})"))

    try:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", args.port or 0))
        results.append((True, "can bind a loopback port"))
    except Exception as exc:
        results.append((False, f"cannot bind port {args.port} ({exc})"))

    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roster", type=Path, help="preseason roster & salary workbook")
    parser.add_argument("etr", type=Path, help="ETR auction values export (.csv or .xlsx)")
    parser.add_argument("--league", type=Path, default=DEFAULT_LEAGUE)
    parser.add_argument("--team", default="Andrew's Team")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--value-column", default="half_ppr")
    parser.add_argument("--tags", type=int, default=1, help="franchise tags held this year")
    parser.add_argument(
        "--post-deadline", type=Path, default=None,
        help="the real post-17-Aug roster workbook; replaces projected rivals with facts",
    )
    parser.add_argument(
        "--db", type=Path, default=ROOT / "data" / "cache" / "auction.db",
        help="sale log; every auction sale is committed here as it is entered",
    )
    parser.add_argument("--no-window", action="store_true", help="serve without a GUI window")
    parser.add_argument("--check", action="store_true",
                        help="verify the environment and exit, without starting anything")
    parser.add_argument("--port", type=int, default=0)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    if args.check:
        results = check_environment(args)
        for ok, message in results:
            print(f"  {'PASS' if ok else 'FAIL'}  {message}")
        failures = [m for ok, m in results if not ok]
        print(f"\n{len(results) - len(failures)}/{len(results)} checks passed")
        raise SystemExit(1 if failures else 0)

    session = Session.load(
        args.league, args.roster, args.etr,
        my_team=args.team, season=args.season, value_column=args.value_column,
    )
    session.tags_available = args.tags
    if args.post_deadline:
        for issue in session.adopt_post_deadline_rosters(args.post_deadline):
            print(f"  warning: {issue}")
    app = create_app(session, AuctionStore(args.db))
    port = args.port or _free_port()

    if args.no_window:
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
        return

    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    threading.Thread(target=server.run, daemon=True).start()

    # Imported late so the server path works with no GUI toolkit present, and
    # wrapped because a missing backend must not end the evening in a
    # traceback. The server is already up by this point, so falling back to a
    # printed URL costs nothing and keeps the draft running.
    try:
        import webview

        webview.create_window(
            f"{session.league.name} — {session.my_team}",
            f"http://127.0.0.1:{port}",
            width=1180, height=900,
        )
        webview.start()
    except Exception as exc:
        print(f"\ncould not open a native window: {exc}")
        print(f"the app is running -- open http://127.0.0.1:{port} in a browser")
        print("(pass --no-window to skip this next time, or --check to diagnose)")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
