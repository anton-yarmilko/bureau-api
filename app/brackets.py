"""Tournament pairing. Pure functions over player ids (strings), no database."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Pairing:
    round: int
    slot: int
    player1: str | None
    player2: str | None


def _next_power_of_two(n: int) -> int:
    size = 1
    while size < n:
        size *= 2
    return size


def _seed_order(size: int) -> list[int]:
    """Standard bracket order so seed 1 and seed 2 can only meet in the final.

    For size 8 returns [1, 8, 4, 5, 2, 7, 3, 6].
    """
    order = [1]
    while len(order) < size:
        total = len(order) * 2 + 1
        order = [x for seed in order for x in (seed, total - seed)]
    return order


def single_elimination(players: list[str]) -> list[Pairing]:
    """All matches of a knockout bracket.

    Players are given in seed order (best first). Missing slots are byes (None).
    Only round 1 has players filled in; later rounds start empty and are filled
    as winners advance.
    """
    if len(players) < 2:
        raise ValueError("need at least 2 players")
    if len(set(players)) != len(players):
        raise ValueError("duplicate players")
    size = _next_power_of_two(len(players))
    order = _seed_order(size)
    slots = [players[s - 1] if s <= len(players) else None for s in order]
    pairings = [
        Pairing(round=1, slot=i, player1=slots[2 * i], player2=slots[2 * i + 1])
        for i in range(size // 2)
    ]
    rounds = size.bit_length() - 1
    for rnd in range(2, rounds + 1):
        for slot in range(size // 2**rnd):
            pairings.append(Pairing(round=rnd, slot=slot, player1=None, player2=None))
    return pairings


def next_position(round_: int, slot: int) -> tuple[int, int, int]:
    """Where the winner of (round, slot) goes: (round, slot, side 1 or 2)."""
    return round_ + 1, slot // 2, 1 if slot % 2 == 0 else 2


def round_robin(players: list[str]) -> list[Pairing]:
    """Everyone plays everyone once (circle method). Byes are dropped."""
    if len(players) < 2:
        raise ValueError("need at least 2 players")
    if len(set(players)) != len(players):
        raise ValueError("duplicate players")
    pool: list[str | None] = list(players)
    if len(pool) % 2:
        pool.append(None)
    n = len(pool)
    pairings: list[Pairing] = []
    for rnd in range(n - 1):
        slot = 0
        for i in range(n // 2):
            a, b = pool[i], pool[n - 1 - i]
            if a is not None and b is not None:
                pairings.append(Pairing(round=rnd + 1, slot=slot, player1=a, player2=b))
                slot += 1
        pool = [pool[0], pool[-1], *pool[1:-1]]
    return pairings
