"""Tournament workflow on top of the pure bracket and rating modules."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import brackets, rating
from app.models import Entry, Match, Player, Rating, Tournament
from app.schemas import MatchResult, PlayerCreate, RatingOut, TournamentCreate


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


def _get(session: Session, model, id_: str):
    obj = session.get(model, id_)
    if obj is None:
        raise NotFoundError(f"{model.__name__.lower()} {id_} not found")
    return obj


def _lock(session: Session, model, id_):
    """Load a row with SELECT ... FOR UPDATE so concurrent writers queue up.

    SQLite ignores the lock (it serialises writers anyway); Postgres enforces it.
    """
    obj = session.get(model, id_, with_for_update=True, populate_existing=True)
    if obj is None:
        raise NotFoundError(f"{model.__name__.lower()} {id_} not found")
    return obj


def _rating(session: Session, player_id: str, game: str, lock: bool = False) -> Rating:
    row = session.get(Rating, (player_id, game), with_for_update=lock, populate_existing=lock)
    if row is None:
        row = Rating(player_id=player_id, game=game, rating=rating.DEFAULT_RATING, games_played=0)
        session.add(row)
    return row


# Players -------------------------------------------------------------------


def create_player(session: Session, data: PlayerCreate) -> Player:
    if data.user_id and session.scalar(select(Player).where(Player.user_id == data.user_id)):
        raise ConflictError("a player with this user_id already exists")
    player = Player(display_name=data.display_name, user_id=data.user_id)
    session.add(player)
    try:
        session.commit()
    except IntegrityError as exc:  # lost a race with an identical request
        session.rollback()
        raise ConflictError("a player with this user_id already exists") from exc
    return player


def get_player(session: Session, player_id: str) -> Player:
    return _get(session, Player, player_id)


def leaderboard(session: Session, game: str, limit: int = 20) -> list[RatingOut]:
    rows = session.execute(
        select(Rating, Player)
        .join(Player, Player.id == Rating.player_id)
        .where(Rating.game == game, Rating.games_played > 0)
        .order_by(Rating.rating.desc(), Rating.games_played.desc())
        .limit(limit)
    ).all()
    return [
        RatingOut(
            player_id=r.player_id,
            display_name=p.display_name,
            game=r.game,
            rating=r.rating,
            games_played=r.games_played,
        )
        for r, p in rows
    ]


# Tournaments ---------------------------------------------------------------


def create_tournament(session: Session, data: TournamentCreate) -> Tournament:
    tournament = Tournament(name=data.name, game=data.game, format=data.format)
    session.add(tournament)
    session.commit()
    return tournament


def get_tournament(session: Session, tournament_id: str) -> Tournament:
    return _get(session, Tournament, tournament_id)


def add_entry(session: Session, tournament_id: str, player_id: str) -> Tournament:
    tournament = _lock(session, Tournament, tournament_id)
    _get(session, Player, player_id)
    if tournament.status != "draft":
        raise ConflictError("entries are closed once the tournament has started")
    if any(e.player_id == player_id for e in tournament.entries):
        raise ConflictError("player is already entered")
    tournament.entries.append(Entry(player_id=player_id, seed=len(tournament.entries) + 1))
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError("player is already entered") from exc
    return tournament


def start_tournament(session: Session, tournament_id: str) -> Tournament:
    tournament = _lock(session, Tournament, tournament_id)
    if tournament.status != "draft":
        raise ConflictError("tournament has already started")
    if len(tournament.entries) < 2:
        raise ConflictError("need at least 2 players to start")

    # Seed by current rating, best first; entry order breaks ties.
    def strength(entry: Entry) -> tuple[float, int]:
        return (-_rating(session, entry.player_id, tournament.game).rating, entry.seed)

    ordered = sorted(tournament.entries, key=strength)
    for seed, entry in enumerate(ordered, start=1):
        entry.seed = seed
    players = [e.player_id for e in ordered]

    if tournament.format == "single_elimination":
        pairings = brackets.single_elimination(players)
    else:
        pairings = brackets.round_robin(players)

    for p in pairings:
        tournament.matches.append(
            Match(round=p.round, slot=p.slot, player1_id=p.player1, player2_id=p.player2)
        )
    tournament.status = "active"
    session.flush()

    if tournament.format == "single_elimination":
        for match in [m for m in tournament.matches if m.round == 1]:
            lone = match.player1_id if match.player2_id is None else None
            if lone is not None:
                match.winner_id = lone  # bye: advances without a game or rating change
                _advance(tournament, match)

    session.commit()
    return tournament


def _find(tournament: Tournament, round_: int, slot: int) -> Match | None:
    return next((m for m in tournament.matches if m.round == round_ and m.slot == slot), None)


def _advance(tournament: Tournament, match: Match) -> None:
    rnd, slot, side = brackets.next_position(match.round, match.slot)
    nxt = _find(tournament, rnd, slot)
    if nxt is None:  # that was the final
        tournament.winner_id = match.winner_id
        tournament.status = "finished"
        return
    if side == 1:
        nxt.player1_id = match.winner_id
    else:
        nxt.player2_id = match.winner_id


def _finish_round_robin(session: Session, tournament: Tournament) -> None:
    if not all(m.is_done for m in tournament.matches):
        return
    points = {e.player_id: 0.0 for e in tournament.entries}
    for m in tournament.matches:
        if m.is_draw:
            points[m.player1_id] += 0.5
            points[m.player2_id] += 0.5
        else:
            points[m.winner_id] += 1.0
    best = max(points.values())
    leaders = [pid for pid, pts in points.items() if pts == best]
    # A shared first place has no single champion; the standings tell the story.
    tournament.winner_id = leaders[0] if len(leaders) == 1 else None
    tournament.status = "finished"


def record_result(session: Session, match_id: str, result: MatchResult) -> Tournament:
    # Lock the tournament first: every result in one tournament is applied in turn,
    # so two submissions for the same match cannot both pass the checks below.
    tournament_id = _get(session, Match, match_id).tournament_id
    tournament = _lock(session, Tournament, tournament_id)
    match = _lock(session, Match, match_id)
    if tournament.status != "active":
        raise ConflictError("tournament is not active")
    if match.is_done:
        raise ConflictError("result already recorded")
    if match.player1_id is None or match.player2_id is None:
        raise ConflictError("match is waiting for its players")
    if result.draw and tournament.format == "single_elimination":
        raise ConflictError("knockout matches need a winner")
    if result.winner_id is not None and result.winner_id not in (
        match.player1_id,
        match.player2_id,
    ):
        raise ConflictError("winner must be one of the two players")

    match.winner_id = result.winner_id
    match.is_draw = result.draw
    match.played_at = datetime.now(UTC)

    # Ratings are shared across tournaments: lock both rows, in a fixed order to avoid deadlocks.
    locked = {
        pid: _rating(session, pid, tournament.game, lock=True)
        for pid in sorted((match.player1_id, match.player2_id))
    }
    r1, r2 = locked[match.player1_id], locked[match.player2_id]
    score = 0.5 if result.draw else (1.0 if result.winner_id == match.player1_id else 0.0)
    change = rating.update(r1.rating, r2.rating, score, r1.games_played, r2.games_played)
    r1.rating, r2.rating = change.a, change.b
    r1.games_played += 1
    r2.games_played += 1

    if tournament.format == "single_elimination":
        _advance(tournament, match)
    else:
        _finish_round_robin(session, tournament)

    session.commit()
    return tournament
