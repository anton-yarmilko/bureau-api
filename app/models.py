import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

GAMES = ("chess", "checkers", "backgammon", "darts")
FORMATS = ("single_elimination", "round_robin")
STATUSES = ("draft", "active", "finished")


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class Player(Base):
    __tablename__ = "players"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    display_name: Mapped[str] = mapped_column(String(40))
    # Supabase auth user id, when the player has an account in the app.
    user_id: Mapped[str | None] = mapped_column(String(36), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Rating(Base):
    __tablename__ = "ratings"

    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"), primary_key=True)
    game: Mapped[str] = mapped_column(String(20), primary_key=True)
    rating: Mapped[float] = mapped_column(Float, default=1200.0)
    games_played: Mapped[int] = mapped_column(Integer, default=0)

    player: Mapped[Player] = relationship()


class Tournament(Base):
    __tablename__ = "tournaments"
    __table_args__ = (
        CheckConstraint(f"game IN {GAMES}", name="ck_tournament_game"),
        CheckConstraint(f"format IN {FORMATS}", name="ck_tournament_format"),
        CheckConstraint(f"status IN {STATUSES}", name="ck_tournament_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(80))
    game: Mapped[str] = mapped_column(String(20))
    format: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(10), default="draft")
    winner_id: Mapped[str | None] = mapped_column(ForeignKey("players.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    entries: Mapped[list["Entry"]] = relationship(
        back_populates="tournament", order_by="Entry.seed", cascade="all, delete-orphan"
    )
    matches: Mapped[list["Match"]] = relationship(
        back_populates="tournament",
        order_by="(Match.round, Match.slot)",
        cascade="all, delete-orphan",
    )


class Entry(Base):
    __tablename__ = "entries"
    __table_args__ = (UniqueConstraint("tournament_id", "player_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tournament_id: Mapped[str] = mapped_column(ForeignKey("tournaments.id"))
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"))
    seed: Mapped[int] = mapped_column(Integer)

    tournament: Mapped[Tournament] = relationship(back_populates="entries")


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (UniqueConstraint("tournament_id", "round", "slot"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tournament_id: Mapped[str] = mapped_column(ForeignKey("tournaments.id"))
    round: Mapped[int] = mapped_column(Integer)
    slot: Mapped[int] = mapped_column(Integer)
    player1_id: Mapped[str | None] = mapped_column(ForeignKey("players.id"))
    player2_id: Mapped[str | None] = mapped_column(ForeignKey("players.id"))
    winner_id: Mapped[str | None] = mapped_column(ForeignKey("players.id"))
    is_draw: Mapped[bool] = mapped_column(Boolean, default=False)
    played_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    tournament: Mapped[Tournament] = relationship(back_populates="matches")

    @property
    def is_done(self) -> bool:
        return self.winner_id is not None or self.is_draw
