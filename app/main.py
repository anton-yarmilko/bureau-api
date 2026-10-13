import secrets
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import services
from app.config import get_settings
from app.db import get_session
from app.schemas import (
    EntryCreate,
    Game,
    MatchResult,
    PlayerCreate,
    PlayerOut,
    RatingOut,
    TournamentCreate,
    TournamentOut,
)

app = FastAPI(
    title="bureau-api",
    version="0.1.0",
    description="Tournaments and Elo ratings for the Bureau bar app.",
)

SessionDep = Annotated[Session, Depends(get_session)]


def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    expected = get_settings().api_key
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "API_KEY is not configured")
    if not (x_api_key and secrets.compare_digest(x_api_key, expected)):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing API key")


Write = Depends(require_api_key)


@app.exception_handler(services.NotFoundError)
def _not_found(_: Request, exc: services.NotFoundError) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=404)


@app.exception_handler(services.ConflictError)
def _conflict(_: Request, exc: services.ConflictError) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=409)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/players", status_code=201, response_model=PlayerOut, dependencies=[Write])
def create_player(data: PlayerCreate, session: SessionDep):
    return services.create_player(session, data)


@app.get("/players/{player_id}", response_model=PlayerOut)
def get_player(player_id: str, session: SessionDep):
    return services.get_player(session, player_id)


@app.get("/leaderboard", response_model=list[RatingOut])
def leaderboard(session: SessionDep, game: Game, limit: Annotated[int, Query(ge=1, le=100)] = 20):
    return services.leaderboard(session, game, limit)


@app.post("/tournaments", status_code=201, response_model=TournamentOut, dependencies=[Write])
def create_tournament(data: TournamentCreate, session: SessionDep):
    return services.create_tournament(session, data)


@app.get("/tournaments/{tournament_id}", response_model=TournamentOut)
def get_tournament(tournament_id: str, session: SessionDep):
    return services.get_tournament(session, tournament_id)


@app.post(
    "/tournaments/{tournament_id}/entries",
    response_model=TournamentOut,
    dependencies=[Write],
)
def add_entry(tournament_id: str, data: EntryCreate, session: SessionDep):
    return services.add_entry(session, tournament_id, data.player_id)


@app.post(
    "/tournaments/{tournament_id}/start",
    response_model=TournamentOut,
    dependencies=[Write],
)
def start_tournament(tournament_id: str, session: SessionDep):
    return services.start_tournament(session, tournament_id)


@app.post("/matches/{match_id}/result", response_model=TournamentOut, dependencies=[Write])
def record_result(match_id: str, data: MatchResult, session: SessionDep):
    return services.record_result(session, match_id, data)
