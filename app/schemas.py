from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator


def _as_utc(value: datetime) -> datetime:
    # SQLite returns naive datetimes; everything we store is UTC, so say so.
    return value if value.tzinfo else value.replace(tzinfo=UTC)


UtcDatetime = Annotated[datetime, AfterValidator(_as_utc)]

Game = Literal["chess", "checkers", "backgammon", "darts"]
Format = Literal["single_elimination", "round_robin"]


class PlayerCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=40)
    user_id: str | None = Field(default=None, max_length=36)


class PlayerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    display_name: str
    user_id: str | None
    created_at: UtcDatetime


class RatingOut(BaseModel):
    player_id: str
    display_name: str
    game: str
    rating: float
    games_played: int


class TournamentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    game: Game
    format: Format = "single_elimination"


class EntryCreate(BaseModel):
    player_id: str


class EntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    player_id: str
    seed: int


class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    round: int
    slot: int
    player1_id: str | None
    player2_id: str | None
    winner_id: str | None
    is_draw: bool
    played_at: UtcDatetime | None


class TournamentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    game: str
    format: str
    status: str
    winner_id: str | None
    created_at: UtcDatetime
    entries: list[EntryOut]
    matches: list[MatchOut]


class MatchResult(BaseModel):
    winner_id: str | None = None
    draw: bool = False

    @model_validator(mode="after")
    def one_outcome(self) -> "MatchResult":
        if self.draw == (self.winner_id is not None):
            raise ValueError("give either winner_id or draw=true, not both")
        return self
