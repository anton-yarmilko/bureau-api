from itertools import combinations

import pytest

from app import brackets


def test_seed_order_keeps_top_seeds_apart():
    assert brackets._seed_order(8) == [1, 8, 4, 5, 2, 7, 3, 6]


def test_eight_players_make_seven_matches():
    pairings = brackets.single_elimination([f"p{i}" for i in range(1, 9)])
    assert len(pairings) == 7
    first = [(p.player1, p.player2) for p in pairings if p.round == 1]
    assert first[0] == ("p1", "p8")


def test_five_players_give_byes_to_top_seeds():
    pairings = brackets.single_elimination(["a", "b", "c", "d", "e"])
    byes = [p.player1 for p in pairings if p.round == 1 and p.player2 is None]
    assert byes == ["a", "b", "c"]
    assert len([p for p in pairings if p.round == 1]) == 4


def test_next_position():
    assert brackets.next_position(1, 0) == (2, 0, 1)
    assert brackets.next_position(1, 1) == (2, 0, 2)
    assert brackets.next_position(1, 3) == (2, 1, 2)


@pytest.mark.parametrize("n", [2, 3, 4, 5, 6, 7])
def test_round_robin_everyone_meets_once(n):
    players = [f"p{i}" for i in range(n)]
    pairings = brackets.round_robin(players)
    met = {frozenset((p.player1, p.player2)) for p in pairings}
    assert len(pairings) == len(met) == len(list(combinations(players, 2)))


def test_round_robin_nobody_plays_twice_in_a_round():
    pairings = brackets.round_robin([f"p{i}" for i in range(6)])
    for rnd in {p.round for p in pairings}:
        seen = [x for p in pairings if p.round == rnd for x in (p.player1, p.player2)]
        assert len(seen) == len(set(seen))


@pytest.mark.parametrize("fn", [brackets.single_elimination, brackets.round_robin])
def test_rejects_bad_input(fn):
    with pytest.raises(ValueError):
        fn(["solo"])
    with pytest.raises(ValueError):
        fn(["a", "a"])
