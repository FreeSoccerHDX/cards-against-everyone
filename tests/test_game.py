import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game import Game, Deck, OWNER_AFK_TRANSFER_SECONDS, EMPTY_GAME_TIMEOUT_SECONDS  # noqa: E402


class FakeSocketIO:
    def __init__(self):
        self.emits = []

    def emit(self, channel, data=None, room=None, **kwargs):
        self.emits.append((channel, data, room))

    def to(self, room):
        return [e for e in self.emits if e[2] == room]


def make_game(players=("anna", "ben", "carl"), start=False):
    socketio = FakeSocketIO()
    users = {name: {"sid": "sid-" + name} for name in players}
    game = Game(socketio, users, players[0], "Testspiel")
    for name in players[1:]:
        game.add_player(name, isSpectator=False)
    if start:
        ok, message = game.start_game()
        assert ok, message
    return game, users, socketio


def add_user(game, users, name, spectator=False):
    users[name] = {"sid": "sid-" + name}
    return game.add_player(name, isSpectator=spectator)


def submit_all(game, skip=()):
    for player in game.active_players:
        if player == game.czar or player in skip or player in game.submitted_white_cards:
            continue
        if game.state != "choosing_cards":
            break
        indices = list(range(game.current_black_card["num_blanks"]))
        ok, message = game.submit_white_cards(player, indices)
        assert ok, message


def non_czar(game):
    return [p for p in game.active_players if p != game.czar]


# ---------- Deck ----------

def test_deck_reshuffles_discard_pile_when_empty():
    deck = Deck(["a", "b"])
    drawn = [deck.draw(), deck.draw()]
    assert sorted(drawn) == ["a", "b"]
    deck.discard(["a"])
    assert deck.draw() == "a"
    # Ablage leer -> kompletter Satz wird neu gemischt
    assert deck.draw() in ("a", "b")


# ---------- Settings ----------

def test_invalid_settings_are_rejected():
    game, _, _ = make_game()
    invalid = game.update_settings({
        "maxWhiteCardsPerPlayer": 10**9,
        "discardRoundInterval": 0,
        "maxPlayers": "abc",
        "publicVisible": "yes",
        "timeToChooseWinner": True,
        "unknown": 1,
        "maxPointsToWin": 7,
    })
    assert set(invalid) == {"maxWhiteCardsPerPlayer", "discardRoundInterval", "maxPlayers",
                            "publicVisible", "timeToChooseWinner", "unknown"}
    assert game.settings["maxWhiteCardsPerPlayer"] == 7
    assert game.settings["discardRoundInterval"] == 10
    assert game.settings["maxPointsToWin"] == 7


def test_password_only_sent_to_owner():
    game, _, _ = make_game()
    game.update_settings({"password": "geheim"})
    assert game.get_socket_game_data("anna")["settings"]["password"] == "geheim"
    assert game.get_socket_game_data("ben")["settings"]["password"] == ""
    assert game.get_socket_game_data("ben")["has_password"] is True


# ---------- Start ----------

def test_start_blocked_while_player_afk():
    game, _, _ = make_game()
    game.mark_player_connection_status("ben", "disconnecting", now=0)
    ok, message = game.start_game()
    assert not ok
    assert "ben" in message
    game.mark_player_connection_status("ben", "connected")
    assert game.start_game()[0]


def test_start_deals_hands():
    game, _, _ = make_game(start=True)
    for player in game.active_players:
        assert len(game.playerCards[player]) == 7
    assert game.czar in game.active_players


# ---------- Submissions ----------

@pytest.mark.parametrize("indices", [[0, 0], ["0"], [True], [99], [-1], "0", None])
def test_invalid_submissions_do_not_change_state(indices):
    game, _, _ = make_game(start=True)
    game.current_black_card = {"card_text": "_____ _____", "num_blanks": 2}
    player = non_czar(game)[0]
    hand_before = list(game.playerCards[player])
    ok, _ = game.submit_white_cards(player, indices)
    assert not ok
    assert player not in game.submitted_white_cards
    assert game.playerCards[player] == hand_before


def test_all_submitted_moves_to_choosing_winner():
    game, _, _ = make_game(start=True)
    submit_all(game)
    assert game.state == "choosing_winner"
    assert sorted(game.player_mapping) == sorted(non_czar(game))


def test_afk_player_is_autosubmitted_when_everyone_else_is_done():
    game, _, _ = make_game(("anna", "ben", "carl", "dora"), start=True)
    afk = non_czar(game)[0]
    game.mark_player_connection_status(afk, "disconnecting", now=0)
    submit_all(game, skip=(afk,))
    assert game.state == "choosing_winner"
    assert afk in game.submitted_white_cards


def test_player_going_afk_after_others_submitted_advances_round():
    game, _, _ = make_game(("anna", "ben", "carl", "dora"), start=True)
    late = non_czar(game)[0]
    submit_all(game, skip=(late,))
    assert game.state == "choosing_cards"
    game.mark_player_connection_status(late, "disconnecting", now=0)
    assert game.state == "choosing_winner"


def test_player_leaving_after_others_submitted_does_not_hang():
    game, _, _ = make_game(("anna", "ben", "carl", "dora"), start=True)
    leaver = non_czar(game)[0]
    submit_all(game, skip=(leaver,))
    game.remove_player(leaver)
    assert game.state == "choosing_winner"


def test_timeout_autosubmits_everyone_missing():
    game, _, _ = make_game(start=True)
    game.currentTimerSeconds = 1
    game.timer_tick()
    assert game.state == "choosing_winner"
    assert sorted(game.submitted_white_cards) == sorted(non_czar(game))


def test_autosubmit_with_small_hand_does_not_crash():
    game, _, _ = make_game(start=True)
    game.current_black_card = {"card_text": "_____ _____ _____", "num_blanks": 3}
    for player in game.active_players:
        game.playerCards[player] = game.playerCards[player][:1]
    game.currentTimerSeconds = 1
    game.timer_tick()
    assert game.state == "choosing_winner"
    for cards in game.submitted_white_cards.values():
        assert len(cards) == 3


# ---------- Winner ----------

def test_winner_who_left_still_gets_point_and_round_continues():
    game, _, _ = make_game(("anna", "ben", "carl", "dora"), start=True)
    submit_all(game)
    winner = game.player_mapping[0]
    assert game.choose_winner(winner, game.czar)[0]
    game.remove_player(winner)
    game.currentTimerSeconds = 1
    game.timer_tick()
    assert game.state == "countdown_next_round"
    assert game.saved_scores[winner] == 1


def test_czar_leaving_during_card_choice_picks_random_winner():
    game, _, _ = make_game(("anna", "ben", "carl", "dora"), start=True)
    game.remove_player(game.czar)
    assert game.czar is None
    submit_all(game)
    assert game.state == "countdown_next_round"
    assert sum(game.scores.values()) == 1


def test_czar_skips_afk_players():
    game, _, _ = make_game(("anna", "ben", "carl", "dora"), start=True)
    czar_index = game.czarIndex
    next_player = game.active_players[(czar_index + 1) % 4]
    game.mark_player_connection_status(next_player, "disconnecting", now=0)
    submit_all(game)
    game.choose_winner(game.player_mapping[0], game.czar)
    game.finalize_winner_choice()
    game.next_round()
    assert game.czar != next_player
    assert game.czar == game.active_players[(czar_index + 2) % 4]


def test_game_ends_when_fewer_than_three_players():
    game, _, _ = make_game(start=True)
    game.remove_player("carl")
    assert game.state == "game_ended"


# ---------- Mid-game join / rejoin ----------

def test_mid_game_join_waits_for_next_round():
    game, users, _ = make_game(start=True)
    ok, _ = add_user(game, users, "emil")
    assert ok
    assert "emil" in game.pending_players
    assert "emil" not in game.active_players
    assert not game.submit_white_cards("emil", [0])[0]

    submit_all(game)
    game.choose_winner(game.player_mapping[0], game.czar)
    game.finalize_winner_choice()
    game.next_round()

    assert "emil" in game.active_players
    assert game.scores["emil"] == 0
    assert len(game.playerCards["emil"]) == 7


def test_rejoin_restores_score():
    game, users, _ = make_game(("anna", "ben", "carl", "dora"), start=True)
    game.scores["dora"] = 3
    game.remove_player("dora")
    add_user(game, users, "dora")
    assert "dora" in game.pending_players

    submit_all(game)
    game.choose_winner(game.player_mapping[0], game.czar)
    game.finalize_winner_choice()
    game.next_round()
    assert game.scores["dora"] >= 3


def test_max_players_counts_pending_players():
    game, users, _ = make_game(start=True)
    game.settings["maxPlayers"] = 4
    assert add_user(game, users, "emil")[0]
    assert not add_user(game, users, "fritz")[0]
    assert add_user(game, users, "gina", spectator=True)[0]


# ---------- Discard round ----------

def test_discard_round_allows_up_to_max_and_rejects_duplicates():
    game, _, _ = make_game(start=True)
    game.state = "countdown_next_round"
    game._enter_discard_round()
    assert not game.submit_discard_cards("anna", [0, 0])[0]
    assert not game.submit_discard_cards("anna", [0, 1, 2, 3])[0]
    assert game.submit_discard_cards("anna", [])[0]
    assert game.submit_discard_cards("ben", [0, 1])[0]
    assert len(game.playerCards["ben"]) == 7
    game.mark_player_connection_status("carl", "disconnecting", now=0)
    assert game.state == "special_discard_round"
    assert game.currentTimerSeconds == 5
    game.currentTimerSeconds = 1
    game.timer_tick()
    assert game.state == "choosing_cards"


# ---------- Owner / housekeeping ----------

def test_owner_afk_transfers_after_five_minutes():
    game, _, socketio = make_game()
    game.mark_player_connection_status("anna", "disconnecting", now=1000)
    assert not game.housekeeping(1000 + OWNER_AFK_TRANSFER_SECONDS - 1)
    assert game.owner == "anna"
    assert not game.housekeeping(1000 + OWNER_AFK_TRANSFER_SECONDS)
    assert game.owner == "ben"
    assert game.pending_notices["anna"]
    assert any(ch == "info" and room == "sid-ben" for ch, _, room in socketio.emits)


def test_game_deleted_after_everyone_gone_for_fifteen_minutes():
    game, _, _ = make_game()
    for player in list(game.active_players):
        game.mark_player_connection_status(player, "disconnecting", now=0)
    assert not game.housekeeping(0)
    assert not game.housekeeping(EMPTY_GAME_TIMEOUT_SECONDS - 1)
    assert game.housekeeping(EMPTY_GAME_TIMEOUT_SECONDS)


def test_owner_leaving_hands_over_even_if_others_afk():
    game, _, _ = make_game()
    game.mark_player_connection_status("ben", "disconnecting", now=0)
    game.mark_player_connection_status("carl", "disconnecting", now=0)
    game.remove_player("anna")
    assert game.owner == "ben"


def test_return_to_lobby_ignores_afk_members():
    game, _, _ = make_game(start=True)
    game.end_game()
    game.mark_player_connection_status("carl", "disconnecting", now=0)
    game.user_return_to_lobby("anna")
    assert game.state == "game_ended"
    game.user_return_to_lobby("ben")
    assert game.state == "lobby"


def test_full_game_runs_to_end():
    game, _, _ = make_game(("anna", "ben", "carl", "dora"), start=True)
    game.settings["maxPointsToWin"] = 2
    game.settings["discardRoundInterval"] = 2
    for _ in range(200):
        if game.state == "game_ended":
            break
        game.currentTimerSeconds = 1
        game.timer_tick()
    assert game.state == "game_ended"
    assert max(game.scores.values()) == 2


# ---------- Bots ----------

def test_bots_fill_up_game_and_play_automatically():
    game, _, _ = make_game(("anna", "ben"))
    ok, bot = game.add_bot()
    assert ok and game.is_bot(bot)
    assert game.start_game()[0]
    if game.czar != bot:
        assert bot in game.submitted_white_cards
    submit_all(game)
    assert game.state == "choosing_winner"


def test_bot_czar_picks_winner_after_short_time():
    game, _, _ = make_game(("anna", "ben"))
    _, bot = game.add_bot()
    game.start_game()
    game.czar = bot
    game.czarIndex = game.active_players.index(bot)
    game.submitted_white_cards = {}
    submit_all(game)
    assert game.currentTimerSeconds <= 8
    game.currentTimerSeconds = 1
    game.timer_tick()
    assert game.state == "countdown_next_round"
    assert sum(game.scores.values()) == 1


def test_bots_cannot_be_owner_or_spectator_and_dont_keep_game_alive():
    game, _, _ = make_game(("anna", "ben"))
    _, bot = game.add_bot()
    assert not game.toggle_role(bot)[0]
    game.remove_player("ben")
    game.remove_player("anna")
    assert game.owner is None
    assert game.human_members() == []
    assert game.housekeeping(0)


def test_bot_names_are_unique_and_respect_max_players():
    game, _, _ = make_game(("anna",))
    game.settings["maxPlayers"] = 3
    names = [game.add_bot()[1] for _ in range(2)]
    assert len(set(names)) == 2
    assert not game.add_bot()[0]


def test_bots_ignored_for_return_to_lobby():
    game, _, _ = make_game(("anna", "ben"))
    game.add_bot()
    game.start_game()
    game.end_game()
    game.user_return_to_lobby("anna")
    game.user_return_to_lobby("ben")
    assert game.state == "lobby"


# ---------- Discard round new cards ----------

def test_discard_draws_new_cards_immediately_and_marks_them():
    game, _, _ = make_game(start=True)
    game.state = "countdown_next_round"
    game._enter_discard_round()
    old_hand = list(game.playerCards["anna"])
    assert game.submit_discard_cards("anna", [0, 1])[0]
    hand = game.playerCards["anna"]
    assert len(hand) == 7
    assert hand[:5] == old_hand[2:]
    data = game.get_socket_game_data("anna")
    assert data["currentPlayerNewCards"] == 2
    assert game.get_socket_game_data("ben")["currentPlayerNewCards"] == 0

    game.submit_discard_cards("ben", [])
    game.submit_discard_cards("carl", [])
    assert game.state == "special_discard_round"
    game.currentTimerSeconds = 1
    game.timer_tick()
    assert game.state == "choosing_cards"
    assert game.get_socket_game_data("anna")["currentPlayerNewCards"] == 0
