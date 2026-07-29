"""Local web server behind the desktop window.

Server-rendered HTML with HTMX for interactions: one language, no build step,
and every click is a form post that swaps a fragment. That matters more here
than it usually would -- the same shell has to carry the live auction in
Phase 3, where a bid needs entering in under two seconds with no network to
wait on.

The server binds to loopback and holds a single in-process session. It is a
desktop app that happens to speak HTTP, not a multi-user service.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.session import Session
from engine.cuts import RetentionPolicy

HERE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(HERE / "templates"))


def _context(request: Request, session: Session) -> dict:
    return {
        "request": request,
        "session": session,
        "league": session.league,
        "rules": session.rules,
        "rows": session.my_rows(),
        "summary": session.summary(),
        "recommendation": session.recommendation(),
        "league_table": session.league_table(),
        "scenarios": session.scenarios(),
    }


def create_app(session: Session) -> FastAPI:
    app = FastAPI(title="FFL-NY Auction Assistant")
    app.state.session = session
    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")

    def board(request: Request) -> HTMLResponse:
        """Every mutation returns the whole board, so nothing can drift out of sync.

        A finer-grained swap would be faster, but the summary, the roster, the
        league table and the scenarios all depend on the same solve -- updating
        one without the others is how a cap figure ends up disagreeing with the
        roster it came from.
        """
        return templates.TemplateResponse(request, "_board.html", _context(request, app.state.session))

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "index.html", _context(request, app.state.session))

    @app.post("/toggle/{player_id}", response_class=HTMLResponse)
    def toggle(request: Request, player_id: str) -> HTMLResponse:
        app.state.session.toggle_cut(player_id)
        return board(request)

    @app.post("/tag/{player_id}", response_class=HTMLResponse)
    def tag(request: Request, player_id: str) -> HTMLResponse:
        app.state.session.toggle_tag(player_id)
        return board(request)

    @app.post("/scenario", response_class=HTMLResponse)
    def scenario(request: Request, policy: str = Form(...)) -> HTMLResponse:
        app.state.session.policy = RetentionPolicy(policy)
        return board(request)

    @app.post("/apply", response_class=HTMLResponse)
    def apply(request: Request) -> HTMLResponse:
        app.state.session.apply_recommendation()
        return board(request)

    @app.post("/reset", response_class=HTMLResponse)
    def reset(request: Request) -> HTMLResponse:
        app.state.session.reset()
        return board(request)

    return app
