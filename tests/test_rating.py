import pytest

from app import rating


def test_equal_players_expect_half():
    assert rating.expected_score(1200, 1200) == pytest.approx(0.5)


def test_400_point_gap_is_ten_to_one():
    assert rating.expected_score(1600, 1200) == pytest.approx(10 / 11)


def test_win_between_equals_moves_by_half_k():
    change = rating.update(1200, 1200, 1.0)
    assert change.a == 1220.0
    assert change.b == 1180.0


def test_draw_between_equals_changes_nothing():
    change = rating.update(1200, 1200, 0.5)
    assert (change.a, change.b) == (1200.0, 1200.0)


def test_upset_gains_more_than_expected_win():
    upset = rating.update(1200, 1600, 1.0).a - 1200
    expected_win = rating.update(1600, 1200, 1.0).a - 1600
    assert upset > expected_win


def test_established_players_move_slower():
    fresh = rating.update(1200, 1200, 1.0, games_a=0).a
    settled = rating.update(1200, 1200, 1.0, games_a=50).a
    assert fresh - 1200 > settled - 1200


def test_rejects_invalid_score():
    with pytest.raises(ValueError):
        rating.update(1200, 1200, 0.7)
