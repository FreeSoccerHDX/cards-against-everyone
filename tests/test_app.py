import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as server  # noqa: E402


@pytest.fixture(autouse=True)
def clean_state():
    # Hintergrund-Timer in Tests nicht starten, tick_all wird direkt aufgerufen
    server.timer_started = True
    server.users.clear()
    server.users_by_token.clear()
    server.users_by_sid.clear()
    server.games.clear()
    yield


def connect():
    return server.socketio.test_client(server.app)


def events(client, name):
    return [e["args"][0] for e in client.get_received() if e["name"] == name]


def login(name):
    client = connect()
    client.emit("set_username", {"username": name})
    token = events(client, "username_set")[0]["token"]
    return client, token


def sid_of(name):
    return server.users[name]["sid"]


def create_game_with(owner_name, *names):
    owner, owner_token = login(owner_name)
    owner.emit("create_game", {"name": "Test", "is_public": True, "password": "pw"})
    game_id = events(owner, "game_created")[0]["game_id"]
    clients = {owner_name: (owner, owner_token)}
    for name in names:
        client, token = login(name)
        client.emit("join_game", {"game_id": game_id, "password": "pw"})
        clients[name] = (client, token)
    for client, _ in clients.values():
        client.get_received()
    return game_id, clients


def test_reconnect_while_old_socket_still_looks_connected():
    game_id, clients = create_game_with("anna", "ben", "carl")
    old_client, token = clients["ben"]

    # Neuer Socket kommt an, bevor der Server den alten als tot erkannt hat
    new_client = connect()
    new_client.emit("reconnect_user", {"token": token})
    received = new_client.get_received()
    reconnected = [e["args"][0] for e in received if e["name"] == "reconnected"][0]
    assert reconnected["success"] is True
    assert reconnected["game"]["game_id"] == game_id
    assert any(e["name"] == "session_taken_over" for e in old_client.get_received())

    # Später Disconnect des alten Sockets darf den Spieler nicht als AFK markieren
    old_client.disconnect()
    assert server.users["ben"]["status"] == "connected"
    assert server.games[game_id].is_status_connected("ben")

    server.tick_all(time.time() + 3600)
    assert "ben" in server.users
    assert "ben" in server.games[game_id].active_players


def test_afk_player_keeps_seat_and_name_is_reserved():
    game_id, clients = create_game_with("anna", "ben", "carl")
    client, token = clients["ben"]
    client.disconnect()
    assert server.users["ben"]["status"] == "disconnecting"

    server.tick_all(time.time() + 120)
    assert "ben" in server.games[game_id].active_players

    # Name ist reserviert
    other = connect()
    other.emit("set_username", {"username": "ben"})
    assert events(other, "username_error")

    # Mit Token zurück ins Spiel
    back = connect()
    back.emit("reconnect_user", {"token": token})
    reconnected = events(back, "reconnected")[0]
    assert reconnected["success"] and reconnected["game"]["game_id"] == game_id
    assert server.games[game_id].is_status_connected("ben")


def test_user_without_game_cleaned_up_after_30_seconds():
    client, token = login("lonely")
    client.disconnect()
    server.tick_all(time.time() + 10)
    assert "lonely" in server.users
    server.tick_all(time.time() + 31)
    assert "lonely" not in server.users
    assert token not in server.users_by_token


def test_invalid_token_requires_new_login():
    client = connect()
    client.emit("reconnect_user", {"token": "gibts-nicht"})
    reconnected = events(client, "reconnected")[0]
    assert reconnected["success"] is False and reconnected["reload"] is True


def test_reconnect_by_username_only_is_not_possible():
    create_game_with("anna", "ben", "carl")
    attacker = connect()
    attacker.emit("reconnect_user", {"username": "ben"})
    assert events(attacker, "reconnected")[0]["success"] is False


def test_logout_frees_name_and_leaves_game():
    game_id, clients = create_game_with("anna", "ben", "carl")
    client, _ = clients["ben"]
    client.emit("logout")
    assert "ben" not in server.users
    assert "ben" not in server.games[game_id].members()

    client.emit("set_username", {"username": "ben"})
    assert events(client, "username_set")


def test_join_link_info_works_without_being_in_a_game():
    game_id, _ = create_game_with("anna")
    client, _ = login("ben")
    client.emit("get_game_info_link_join", {"game_id": game_id})
    info = events(client, "game_info_link_join")[0]
    assert info["id"] == game_id and info["has_password"] is True


def test_password_not_sent_to_non_owner():
    game_id, clients = create_game_with("anna", "ben")
    client, _ = clients["ben"]
    client.emit("get_game_state")
    assert events(client, "game_state_update")[0]["settings"]["password"] == ""
    owner, _ = clients["anna"]
    owner.emit("get_game_state")
    assert events(owner, "game_state_update")[0]["settings"]["password"] == "pw"


def test_kicked_player_leaves_room():
    game_id, clients = create_game_with("anna", "ben", "carl")
    owner, _ = clients["anna"]
    kicked, _ = clients["ben"]
    owner.emit("kick_player", {"username": "ben"})
    assert events(kicked, "kicked_from_game")
    server.socketio.emit("timer_sync", {"time_left": 1}, room=game_id)
    assert not events(kicked, "timer_sync")
    assert server.users["ben"]["game_id"] is None


def test_joining_other_game_leaves_previous_one():
    first_id, clients = create_game_with("anna", "ben")
    second_id, _ = create_game_with("carl")
    client, _ = clients["ben"]
    client.emit("join_game", {"game_id": second_id, "password": "wrong"})
    assert "ben" in server.games[first_id].members()
    client.emit("join_game", {"game_id": second_id, "password": "pw"})
    assert "ben" not in server.games[first_id].members()
    assert "ben" in server.games[second_id].members()


def test_start_blocked_by_afk_player():
    game_id, clients = create_game_with("anna", "ben", "carl")
    clients["carl"][0].disconnect()
    owner, _ = clients["anna"]
    owner.emit("start_game")
    errors = events(owner, "error")
    assert errors and "carl" in errors[0]["message"]
    assert server.games[game_id].state == "lobby"


def test_force_role_reports_failure():
    game_id, clients = create_game_with("anna", "ben", "carl")
    server.games[game_id].settings["maxPlayers"] = 3
    owner, _ = clients["anna"]
    owner.emit("force_role", {"username": "ben"})
    owner.get_received()
    clients["dora"] = login("dora")
    clients["dora"][0].emit("join_game", {"game_id": game_id, "password": "pw"})
    owner.get_received()
    owner.emit("force_role", {"username": "ben"})
    assert events(owner, "error")


def test_owner_adds_bot_and_bot_names_reserved():
    game_id, clients = create_game_with("anna", "ben")
    owner, _ = clients["anna"]
    owner.emit("add_bot")
    assert len(server.games[game_id].bots) == 1
    clients["ben"][0].emit("add_bot")
    assert events(clients["ben"][0], "error")

    other = connect()
    other.emit("set_username", {"username": "🤖 Bot 9"})
    assert events(other, "username_error")


def test_game_deleted_when_only_bots_left():
    game_id, clients = create_game_with("anna")
    owner, _ = clients["anna"]
    owner.emit("add_bot")
    owner.emit("leave_game")
    assert game_id not in server.games
