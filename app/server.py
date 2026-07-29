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
from app.store import AuctionStore
from data.models import Player
from data.name_matching import match_players, resolve_one
from engine.cuts import RetentionPolicy

HERE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(HERE / "templates"))

# Name resolution is deliberately stricter at the auction than elsewhere.
# `resolve_one` auto-commits whenever one candidate is clearly ahead of the
# rest -- but "clearly ahead" is satisfied by a *single* loose match too, so
# typing a player who is already rostered or sold can silently land on some
# other player who happens to share a token ("Rival Star" -> "Rival Filler").
# At a live auction that misfiling is expensive and easy to miss, so a match
# has to be strong in absolute terms, not merely the best of a thin field.
AUCTION_MATCH_THRESHOLD = 85.0


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


def _auction_context(request: Request, app: FastAPI, notice: str = "", error: str = "") -> dict:
    auction = app.state.auction
    session = app.state.session
    return {
        "request": request,
        "session": session,
        "rules": session.rules,
        "auction": auction,
        "me": auction.status(auction.my_team),
        "teams": auction.all_status(),
        "board": auction.board(limit=30),
        "nominations": auction.nomination_candidates(),
        "inflation": auction.inflation(),
        "recent": list(reversed(auction.sales[-8:])),
        "notice": notice,
        "error": error,
        "stale": app.state.auction_opened_from != (
            frozenset(session.cut), frozenset(session.tagged), session.policy
        ),
    }


def _as_players(auction) -> list[Player]:
    """Adapt the auction board to the shape `name_matching` expects."""
    return [
        Player(
            player_id=info.player_id, name=info.name, nfl_team=info.nfl_team,
            position=info.position, eligible_positions=frozenset({info.position}),
        )
        for info in auction.available()
        if info.position is not None
    ]


def create_app(session: Session, store: AuctionStore | None = None) -> FastAPI:
    app = FastAPI(title="FFL-NY Auction Assistant")
    app.state.session = session
    app.state.store = store
    app.state.auction = None
    app.state.auction_opened_from = None
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

    # -- live auction -------------------------------------------------------

    def _decisions() -> tuple:
        session = app.state.session
        return (frozenset(session.cut), frozenset(session.tagged), session.policy)

    def ensure_auction():
        """Open the auction lazily, and reopen it if the cut plan has changed.

        Lazily because the cut/keep decisions have to be settled first -- the
        auction's opening state *is* the post-deadline roster.

        Rebuilding on change matters more than it looks. Without it, whichever
        request happened to touch this page first freezes the opening rosters
        forever, so going back to fix a cut leaves the auction quietly running
        off the old plan. Once real sales exist the opening state is frozen
        deliberately instead, since rebuilding would strand the sale log
        against rosters it was never recorded against; the page says so rather
        than silently disagreeing with the board behind it.
        """
        auction = app.state.auction
        if auction is None or (
            app.state.auction_opened_from != _decisions() and not auction.sales
        ):
            app.state.auction = app.state.session.start_auction()
            app.state.auction_opened_from = _decisions()
            if app.state.store is not None:
                app.state.auction.replay(app.state.store.load())
        return app.state.auction

    def auction_board(request: Request, notice: str = "", error: str = "") -> HTMLResponse:
        return templates.TemplateResponse(
            request, "_auction.html", _auction_context(request, app, notice, error)
        )

    @app.get("/auction", response_class=HTMLResponse)
    def auction_page(request: Request) -> HTMLResponse:
        ensure_auction()
        return templates.TemplateResponse(
            request, "auction.html", _auction_context(request, app)
        )

    @app.post("/auction/sale", response_class=HTMLResponse)
    def record_sale(
        request: Request,
        player: str = Form(...),
        price: int = Form(...),
        team: str = Form(...),
    ) -> HTMLResponse:
        auction = ensure_auction()
        resolved = resolve_one(player, _as_players(auction), threshold=AUCTION_MATCH_THRESHOLD)
        if resolved is None:
            # Never guess mid-auction: recording the wrong player costs far
            # more than asking which one was meant.
            hints = [p.name for p, _ in match_players(player, _as_players(auction), limit=4)]
            suffix = f" — did you mean {', '.join(hints)}?" if hints else ""
            return auction_board(request, error=f"No clear match for {player!r}{suffix}")

        try:
            sale = auction.record(resolved.player_id, team, price)
        except ValueError as exc:
            return auction_board(request, error=str(exc))

        if app.state.store is not None:
            app.state.store.append(sale)
        return auction_board(
            request, notice=f"{sale.player_name} → {sale.team} at ${sale.price}"
        )

    @app.post("/auction/undo", response_class=HTMLResponse)
    def undo_sale(request: Request) -> HTMLResponse:
        auction = ensure_auction()
        undone = auction.undo()
        if undone is None:
            return auction_board(request, error="Nothing to undo")
        if app.state.store is not None:
            app.state.store.pop()
        return auction_board(request, notice=f"Undid {undone.player_name} at ${undone.price}")

    return app
