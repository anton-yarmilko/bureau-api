"""Elo rating math. Pure functions, no I/O, so they are easy to test."""

from dataclasses import dataclass

DEFAULT_RATING = 1200.0
PROVISIONAL_GAMES = 30
K_PROVISIONAL = 40.0
K_ESTABLISHED = 20.0


@dataclass(frozen=True)
class RatingChange:
    a: float
    b: float


def expected_score(rating_a: float, rating_b: float) -> float:
    """Probability-like expected score of A against B (0..1)."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def k_factor(games_played: int) -> float:
    """New players move faster until their rating settles."""
    return K_PROVISIONAL if games_played < PROVISIONAL_GAMES else K_ESTABLISHED


def update(
    rating_a: float,
    rating_b: float,
    score_a: float,
    games_a: int = 0,
    games_b: int = 0,
) -> RatingChange:
    """Return new ratings after one game.

    score_a is 1.0 for an A win, 0.5 for a draw, 0.0 for an A loss.
    """
    if score_a not in (0.0, 0.5, 1.0):
        raise ValueError("score_a must be 0, 0.5 or 1")
    exp_a = expected_score(rating_a, rating_b)
    new_a = rating_a + k_factor(games_a) * (score_a - exp_a)
    new_b = rating_b + k_factor(games_b) * ((1.0 - score_a) - (1.0 - exp_a))
    return RatingChange(a=round(new_a, 1), b=round(new_b, 1))
