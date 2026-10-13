import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import TEST_DATABASE_URL

from app.config import get_settings


def _tournament(client, players, fmt="single_elimination", game="chess"):
    t = client.post("/tournaments", json={"name": "Friday cup", "game": game, "format": fmt})
    assert t.status_code == 201
    tid = t.json()["id"]
    for pid in players:
        assert (
            client.post(f"/tournaments/{tid}/entries", json={"player_id": pid}).status_code == 200
        )
    started = client.post(f"/tournaments/{tid}/start")
    assert started.status_code == 200
    return started.json()


def _playable(t):
    return [
        m
        for m in t["matches"]
        if m["player1_id"] and m["player2_id"] and not m["winner_id"] and not m["is_draw"]
    ]


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_player_roundtrip(client):
    created = client.post("/players", json={"display_name": "Oksana"}).json()
    assert client.get(f"/players/{created['id']}").json()["display_name"] == "Oksana"
    assert client.get("/players/nope").status_code == 404


def test_duplicate_user_id_conflicts(client):
    body = {"display_name": "A", "user_id": "11111111-1111-1111-1111-111111111111"}
    assert client.post("/players", json=body).status_code == 201
    assert client.post("/players", json=body).status_code == 409


def test_knockout_runs_to_a_winner(client, make_players):
    players = make_players("A", "B", "C", "D", "E")
    t = _tournament(client, players)
    assert t["status"] == "active"
    # Always let player1 win until the bracket is done.
    while t["status"] == "active":
        match = _playable(t)[0]
        res = client.post(f"/matches/{match['id']}/result", json={"winner_id": match["player1_id"]})
        assert res.status_code == 200
        t = res.json()
    assert t["status"] == "finished"
    assert t["winner_id"] in players
    # 5 players need exactly 4 real games.
    played = [m for m in t["matches"] if m["played_at"]]
    assert len(played) == 4


def test_ratings_update_and_leaderboard(client, make_players):
    a, b = make_players("A", "B")
    t = _tournament(client, [a, b])
    match = _playable(t)[0]
    client.post(f"/matches/{match['id']}/result", json={"winner_id": a})
    board = client.get("/leaderboard", params={"game": "chess"}).json()
    assert [row["player_id"] for row in board] == [a, b]
    assert board[0]["rating"] > 1200 > board[1]["rating"]
    assert board[0]["games_played"] == 1


def test_round_robin_with_draws(client, make_players):
    players = make_players("A", "B", "C", "D")
    t = _tournament(client, players, fmt="round_robin")
    assert len(t["matches"]) == 6
    for m in t["matches"]:
        res = client.post(f"/matches/{m['id']}/result", json={"draw": True})
        assert res.status_code == 200
        t = res.json()
    assert t["status"] == "finished"


def test_rules_are_enforced(client, make_players):
    a, b, c = make_players("A", "B", "C")
    t = _tournament(client, [a, b])
    match = _playable(t)[0]
    url = f"/matches/{match['id']}/result"
    assert client.post(url, json={"draw": True}).status_code == 409  # knockout needs a winner
    assert client.post(url, json={"winner_id": c}).status_code == 409  # not in this match
    assert client.post(url, json={}).status_code == 422  # no outcome
    assert client.post(url, json={"winner_id": a}).status_code == 200
    assert client.post(url, json={"winner_id": a}).status_code == 409  # already played
    assert client.post(f"/tournaments/{t['id']}/entries", json={"player_id": c}).status_code == 409


def test_cannot_start_with_one_player(client, make_players):
    (a,) = make_players("A")
    tid = client.post("/tournaments", json={"name": "x", "game": "darts"}).json()["id"]
    client.post(f"/tournaments/{tid}/entries", json={"player_id": a})
    assert client.post(f"/tournaments/{tid}/start").status_code == 409


def test_api_key_protects_writes(client, monkeypatch):
    body = {"display_name": "A"}
    assert client.post("/players", json=body, headers={"X-API-Key": ""}).status_code == 401
    assert client.post("/players", json=body, headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.post("/players", json=body).status_code == 201
    assert client.get("/health", headers={"X-API-Key": ""}).status_code == 200  # reads stay open


def test_writes_fail_closed_without_configured_key(client, monkeypatch):
    monkeypatch.delenv("API_KEY")
    get_settings.cache_clear()
    assert client.post("/players", json={"display_name": "A"}).status_code == 503


def test_round_robin_tie_has_no_single_winner(client, make_players):
    players = make_players("A", "B", "C")
    t = _tournament(client, players, fmt="round_robin")
    for m in t["matches"]:
        t = client.post(f"/matches/{m['id']}/result", json={"draw": True}).json()
    assert t["status"] == "finished"
    assert t["winner_id"] is None


def test_round_robin_clear_leader_wins(client, make_players):
    a, b, c = make_players("A", "B", "C")
    t = _tournament(client, [a, b, c], fmt="round_robin")
    for m in t["matches"]:
        winner = a if a in (m["player1_id"], m["player2_id"]) else m["player1_id"]
        t = client.post(f"/matches/{m['id']}/result", json={"winner_id": winner}).json()
    assert t["winner_id"] == a


def test_timestamps_are_utc(client):
    player = client.post("/players", json={"display_name": "A"}).json()
    again = client.get(f"/players/{player['id']}").json()
    assert again["created_at"].endswith(("Z", "+00:00"))


def test_unknown_player_cannot_enter(client):
    tid = client.post("/tournaments", json={"name": "x", "game": "chess"}).json()["id"]
    res = client.post(f"/tournaments/{tid}/entries", json={"player_id": "ghost"})
    assert res.status_code == 404


@pytest.mark.skipif(TEST_DATABASE_URL.startswith("sqlite"), reason="row locks need Postgres")
def test_concurrent_results_apply_once(client, make_players):
    a, b = make_players("A", "B")
    t = _tournament(client, [a, b])
    url = f"/matches/{_playable(t)[0]['id']}/result"
    barrier = threading.Barrier(4)

    def post(winner):
        barrier.wait()
        return client.post(url, json={"winner_id": winner}).status_code

    with ThreadPoolExecutor(4) as pool:
        codes = sorted(pool.map(post, [a, b, a, b]))
    assert codes == [200, 409, 409, 409]
    board = client.get("/leaderboard", params={"game": "chess"}).json()
    assert [row["games_played"] for row in board] == [1, 1]
