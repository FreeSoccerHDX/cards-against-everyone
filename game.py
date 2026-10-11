from questions import CARDS_QUESTIONS
from answers import CARDS_ANSWERS
import uuid
import random

# Owner wird nach so vielen Sekunden Inaktivität an den nächsten verbundenen Spieler übergeben
OWNER_AFK_TRANSFER_SECONDS = 5 * 60
# Spiel wird gelöscht, wenn so lange niemand verbunden ist
EMPTY_GAME_TIMEOUT_SECONDS = 15 * 60

# Erlaubte Einstellungen: key -> (typ, min, max) | bei str gilt min/max für die Länge
SETTINGS_SCHEMA = {
    "gameName": (str, 1, 30),
    "publicVisible": (bool, None, None),
    "publicVisibleDuringGame": (bool, None, None),
    "password": (str, 0, 50),
    "maxWhiteCardsPerPlayer": (int, 5, 50),
    "maxPointsToWin": (int, 1, 2000),
    "maxRounds": (int, 1, 10000),
    "timeToChooseWhiteCards": (int, 10, 3600),
    "timeToChooseWinner": (int, 10, 3600),
    "timeAfterWinnerChosen": (int, 3, 600),
    "maxPlayers": (int, 3, 42),
    "discardRoundActive": (bool, None, None),
    "discardRoundInterval": (int, 1, 100),
    "discardMaxCards": (int, 1, 20),
    "discardTime": (int, 10, 600),
}


def validate_setting(key, value):
    """Gibt (ok, bereinigter_wert) zurück"""
    if key not in SETTINGS_SCHEMA:
        return False, None
    typ, min_value, max_value = SETTINGS_SCHEMA[key]
    if typ is bool:
        return (True, value) if isinstance(value, bool) else (False, None)
    if typ is int:
        # bool ist eine Unterklasse von int und daher explizit ausgeschlossen
        if isinstance(value, bool) or not isinstance(value, int):
            return False, None
        return (True, value) if min_value <= value <= max_value else (False, None)
    if typ is str:
        if not isinstance(value, str):
            return False, None
        value = value.strip()
        return (True, value) if min_value <= len(value) <= max_value else (False, None)
    return False, None


def parse_card_indices(indices, hand_size):
    """Prüft eine Liste von Kartenindizes. Gibt (indices, error) zurück."""
    if not isinstance(indices, list):
        return None, "Ungültige Kartenauswahl"
    for index in indices:
        if isinstance(index, bool) or not isinstance(index, int):
            return None, "Ungültige Kartenauswahl"
        if index < 0 or index >= hand_size:
            return None, "Karte(n) nicht in deinem Blatt"
    if len(set(indices)) != len(indices):
        return None, "Jede Karte darf nur einmal gewählt werden"
    return indices, None


class Deck:
    """Gemischter Kartenstapel mit Ablage. Ist der Stapel leer, wird die Ablage neu gemischt."""

    def __init__(self, all_cards):
        self.all_cards = all_cards
        self.draw_pile = []
        self.discard_pile = []
        self.reset()

    def reset(self):
        self.draw_pile = list(self.all_cards)
        random.shuffle(self.draw_pile)
        self.discard_pile = []

    def draw(self):
        if not self.draw_pile:
            self.draw_pile = self.discard_pile if self.discard_pile else list(self.all_cards)
            self.discard_pile = []
            random.shuffle(self.draw_pile)
        return self.draw_pile.pop()

    def discard(self, cards):
        self.discard_pile.extend(cards)


class Game:
    def __init__(self, socketio, global_player_data, ownerName, gameName, isPublicVisible=True, password=""):
        self.socketio = socketio
        self.global_player_data = global_player_data
        self.game_id = str(uuid.uuid4())
        self.owner = ownerName      # Owner's player name
        self.active_players = [ownerName]   # Spieler, die aktuell mitspielen (auch AFK-Spieler behalten ihren Platz)
        self.pending_players = []           # Spieler, die während eines laufenden Spiels beigetreten sind -> steigen nächste Runde ein
        self.spectators = []                # List of spectator names
        self.player_status = {ownerName: 'connected'}   # playerName: 'connected' | 'disconnecting'
        self.disconnected_at = {}           # playerName: timestamp seit wann die Verbindung weg ist
        self.no_connected_since = None      # timestamp seit wann niemand mehr verbunden ist
        self.pending_notices = {}           # playerName: [nachrichten], die beim Reconnect zugestellt werden

        # Game variables
        self.history = []          # list of past rounds
        self.current_round = 0     # current round number
        self.playerCards = {}   # playerName: list of white cards
        self.current_black_card = {} # current black card -> card_text: str, num_blanks: int
        self.winning_white_cards = {}  # winning white cards in current round
        self.submitted_white_cards = {}  # playerName: [white_card(s)]
        self.player_mapping = []    # List of playerNames random order for displaying submitted cards
        self.scores = {}           # playerName: score
        self.saved_scores = {}     # playerName: score von Spielern, die das laufende Spiel verlassen haben
        self.czarIndex = 0      # index of current czar in active_players
        self.czar = None           # playerName of current czar
        self.state = 'lobby'  # 'lobby', 'choosing_cards', 'choosing_winner', 'countdown_next_round', 'game_ended', 'special_discard_round'
        self.currentTimerTotalSeconds = 0  # total seconds for current timer
        self.currentTimerSeconds = 0      # remaining seconds for current timer
        self.paused = False # whether the game is paused (owner can pause during choosing phases)
        self.winner_chosen = False
        self.current_czar_selected_player = None
        self.choosing_playerName = None
        self.current_reactions = {}  # playerName: { to_player_index: points }
        self.returned_to_lobby = []  # list of playerNames who have returned to lobby after game ended

        self.white_deck = Deck(CARDS_ANSWERS)
        self.black_deck = Deck(CARDS_QUESTIONS)

        # Game Settings
        self.settings = {
            "gameName": ownerName + "'s Spiel",
            "publicVisible": True,
            "publicVisibleDuringGame": False,
            "password": "",
            "maxWhiteCardsPerPlayer": 7,
            "maxPointsToWin": 5,
            "maxRounds": 25,
            "timeToChooseWhiteCards": 60,
            "timeToChooseWinner": 60,
            "timeAfterWinnerChosen": 15,
            "maxPlayers": 10,
            "discardRoundActive": True,
            "discardRoundInterval": 10,
            "discardMaxCards": 3,
            "discardTime": 30
        }
        self.update_settings({
            "gameName": gameName,
            "publicVisible": isPublicVisible,
            "password": password,
        })

    # ########################################
    #       Helpers
    # ########################################

    def members(self):
        return self.active_players + self.pending_players + self.spectators

    def is_member(self, playerName):
        return playerName in self.members()

    def is_status_connected(self, playerName):
        return self.player_status.get(playerName) == 'connected'

    def is_game_started(self):
        return self.state != 'lobby' and self.state != 'game_ended'

    def _sid(self, playerName):
        user = self.global_player_data.get(playerName)
        return user.get('sid') if user else None

    def _emit_to_player(self, playerName, channel, data):
        sid = self._sid(playerName)
        if sid:
            self.socketio.emit(channel, data, room=sid)

    def _non_czar_players(self):
        return [p for p in self.active_players if p != self.czar]

    def _promote_pending_players(self):
        for playerName in self.pending_players:
            self.active_players.append(playerName)
            if self.is_game_started():
                self.scores[playerName] = self.saved_scores.pop(playerName, 0)
        self.pending_players = []

    def _pick_new_owner(self, exclude=None):
        candidates = [m for m in self.members() if m != exclude]
        for member in candidates:
            if self.is_status_connected(member):
                return member
        return candidates[0] if candidates else None

    def _add_point(self, playerName):
        if playerName in self.scores:
            self.scores[playerName] += 1
        else:
            self.saved_scores[playerName] = self.saved_scores.get(playerName, 0) + 1

    def _set_timer(self, seconds):
        self.currentTimerTotalSeconds = seconds
        self.currentTimerSeconds = seconds

    def _draw_hand(self, playerName, size):
        hand = self.playerCards.setdefault(playerName, [])
        while len(hand) < size:
            hand.append(self.white_deck.draw())
        return hand

    def _take_cards(self, playerName, indices):
        """Entfernt die Karten an den gegebenen Indizes aus der Hand und gibt sie zurück"""
        hand = self.playerCards.get(playerName, [])
        cards = [hand[i] for i in indices]
        for i in sorted(indices, reverse=True):
            hand.pop(i)
        return cards

    # ########################################
    #       Settings
    # ########################################

    def update_settings(self, newSettings):
        """Übernimmt gültige Einstellungen. Gibt Liste der ungültigen Keys zurück."""
        invalid = []
        if not isinstance(newSettings, dict):
            return ["settings"]
        for key, value in newSettings.items():
            if value is None:
                continue
            ok, cleaned = validate_setting(key, value)
            if ok:
                self.settings[key] = cleaned
            else:
                invalid.append(key)
        return invalid

    # ########################################
    #       Socket Data
    # ########################################

    def send_socket_game_update_for_all(self, channel="game_state_update", extra=None):
        for player in self.members():
            data = self.get_socket_game_data(current_playerName=player)
            payload = data if extra is None else {**extra, "game": data}
            self._emit_to_player(player, channel, payload)

    def broadcast_event_to_game(self, channel, data):
        for player in self.members():
            self._emit_to_player(player, channel, data)

    def get_socket_game_data(self, current_playerName: str = None):
        settings = dict(self.settings)
        # Passwort nur an den Owner schicken (braucht es für das Einstellungsfeld)
        if current_playerName != self.owner:
            settings["password"] = ""

        return {
            "game_id": self.game_id,
            "owner": self.owner,
            "active_players": self.active_players,
            "pending_players": self.pending_players,
            "player_status": self.player_status,
            "spectators": self.spectators,
            # History wird nur am Spielende angezeigt
            "history": self.history if self.state == 'game_ended' else [],
            "current_round": self.current_round,
            "currentPlayerCards": self.playerCards.get(current_playerName, []) if current_playerName else [],
            "current_black_card": self.current_black_card,
            "player_mapping": self.player_mapping,
            "winning_white_cards": self.winning_white_cards,
            "submitted_white_cards": self.submitted_white_cards if self.state != 'special_discard_round' else {p: [] for p in self.submitted_white_cards},
            "scores": self.scores,
            "czarIndex": self.czarIndex,
            "czar": self.czar,
            "state": self.state,
            "currentTimerTotalSeconds": self.currentTimerTotalSeconds,
            "currentTimerSeconds": self.currentTimerSeconds,
            "paused": self.paused,
            "winner_chosen": self.winner_chosen,
            "current_czar_selected_player": self.current_czar_selected_player if self.czar == current_playerName else None,
            "player_reactions": self.current_reactions.get(current_playerName, {}),
            "returned_to_lobby": self.returned_to_lobby,
            "has_password": bool(self.settings["password"]),
            "settings": settings
        }

    # ########################################
    #       Members
    # ########################################

    def add_player(self, playerName, isSpectator):
        if not playerName:
            return False, "Ungültiger Spielername"

        if self.is_member(playerName):
            self.player_status[playerName] = 'connected'
            self.disconnected_at.pop(playerName, None)
            return True, "Wieder beigetreten"

        if isSpectator:
            self.spectators.append(playerName)
        else:
            if len(self.active_players) + len(self.pending_players) >= self.settings["maxPlayers"]:
                return False, "Maximale Spieleranzahl erreicht"
            if self.is_game_started():
                # Steigt in der nächsten Runde ein
                self.pending_players.append(playerName)
            else:
                self.active_players.append(playerName)

        self.player_status[playerName] = 'connected'
        self.disconnected_at.pop(playerName, None)
        return True, "Spieler hinzugefügt"

    def remove_player(self, playerName):
        if not self.is_member(playerName):
            return False

        if playerName in self.spectators:
            self.spectators.remove(playerName)
        if playerName in self.pending_players:
            self.pending_players.remove(playerName)

        if playerName in self.active_players:
            index = self.active_players.index(playerName)
            if self.is_game_started():
                # Punkte merken, falls der Spieler wieder beitritt
                self.saved_scores[playerName] = self.scores.pop(playerName, 0)
                self.white_deck.discard(self.playerCards.pop(playerName, []))
                # czarIndex zeigt weiter auf denselben Spieler bzw. auf den davor
                if index <= self.czarIndex:
                    self.czarIndex -= 1
                if self.czar == playerName:
                    self.czar = None
                if self.state == 'choosing_cards' and playerName in self.submitted_white_cards:
                    self.white_deck.discard(self.submitted_white_cards.pop(playerName))
                if self.state == 'special_discard_round':
                    self.submitted_white_cards.pop(playerName, None)
                # In 'choosing_winner' bleibt die Abgabe bestehen, sie kann weiterhin gewinnen
                self.current_reactions.pop(playerName, None)
            self.active_players.remove(playerName)

        self.player_status.pop(playerName, None)
        self.disconnected_at.pop(playerName, None)
        self.pending_notices.pop(playerName, None)
        if playerName in self.returned_to_lobby:
            self.returned_to_lobby.remove(playerName)

        if self.owner == playerName:
            self.owner = self._pick_new_owner(exclude=playerName)

        if self.is_game_started():
            if len(self.active_players) + len(self.pending_players) < 3:
                self.end_game()
            elif self.state == 'choosing_cards':
                self._advance_if_all_submitted()
            elif self.state == 'special_discard_round':
                self._advance_if_all_discarded()
        elif self.state == 'game_ended':
            self._check_all_returned_to_lobby()

        return True

    def toggle_role(self, playerName):
        if self.is_game_started():
            return False, "Spiel bereits gestartet"

        if playerName in self.spectators:
            # switch to player
            if len(self.active_players) + len(self.pending_players) >= self.settings["maxPlayers"]:
                return False, "Maximale Spieleranzahl erreicht"
            self.spectators.remove(playerName)
            self.active_players.append(playerName)
            return True, "Spieler"

        if playerName in self.active_players:
            # switch to spectator
            self.active_players.remove(playerName)
            self.spectators.append(playerName)
            return True, "Zuschauer"

        return False, "Spieler nicht gefunden"

    def is_pending_player(self, playerName):
        """Spieler gehört zum Spiel, ist aber gerade nicht verbunden (für die Lobby-Liste)"""
        if not playerName or not self.is_member(playerName):
            return False
        return not self.is_status_connected(playerName)

    def mark_player_connection_status(self, playerName, status, now=None):
        if playerName not in self.player_status:
            return False

        self.player_status[playerName] = status
        if status == 'connected':
            self.disconnected_at.pop(playerName, None)
        else:
            self.disconnected_at[playerName] = now

        self.socketio.emit('player_status_changed', {
            'username': playerName,
            'status': status
        }, room=self.game_id)

        # Fehlen nur noch AFK-Spieler, geht es direkt weiter
        if status != 'connected':
            advanced = False
            if self.state == 'choosing_cards':
                advanced = self._advance_if_all_submitted()
            elif self.state == 'special_discard_round':
                advanced = self._advance_if_all_discarded()
            elif self.state == 'game_ended':
                advanced = self._check_all_returned_to_lobby()
            if advanced:
                self.send_socket_game_update_for_all()

        return True

    def housekeeping(self, now):
        """Wird jede Sekunde aufgerufen. Gibt True zurück, wenn das Spiel gelöscht werden soll."""
        members = self.members()
        if not members:
            return True

        if any(self.is_status_connected(m) for m in members):
            self.no_connected_since = None
        elif self.no_connected_since is None:
            self.no_connected_since = now
        elif now - self.no_connected_since >= EMPTY_GAME_TIMEOUT_SECONDS:
            return True

        # Owner inaktiv -> Owner-Rolle an nächsten verbundenen Spieler übergeben
        owner = self.owner
        owner_afk_since = self.disconnected_at.get(owner)
        if owner and not self.is_status_connected(owner) and owner_afk_since is not None \
                and now - owner_afk_since >= OWNER_AFK_TRANSFER_SECONDS:
            new_owner = next((m for m in members if m != owner and self.is_status_connected(m)), None)
            if new_owner:
                self.owner = new_owner
                self.pending_notices.setdefault(owner, []).append(
                    f"Du warst länger als 5 Minuten inaktiv – {new_owner} ist jetzt Spielleiter.")
                for member in self.members():
                    if member == new_owner:
                        message = f"{owner} war länger als 5 Minuten inaktiv – du bist jetzt Spielleiter."
                    else:
                        message = f"{owner} war inaktiv – {new_owner} ist jetzt Spielleiter."
                    self._emit_to_player(member, 'info', {'message': message})
                self.send_socket_game_update_for_all()

        return False

    # ########################################
    #       Game Flow
    # ########################################

    def start_game(self):
        if self.is_game_started():
            return False, "Spiel läuft bereits"

        self._promote_pending_players()

        if len(self.active_players) < 3:
            return False, "Mindestens 3 aktive Spieler erforderlich (Zuschauer zählen nicht)"

        afk_players = [p for p in self.active_players if not self.is_status_connected(p)]
        if afk_players:
            return False, "Warte auf: " + ", ".join(afk_players)

        self.broadcast_event_to_game("sound_event", "game_start")

        self.state = 'choosing_cards'
        self.current_round = 0
        self.paused = False
        self.returned_to_lobby = []
        self.submitted_white_cards = {}
        self.player_mapping = []
        self.history = []
        self.playerCards = {}
        self.winning_white_cards = {}
        self.current_reactions = {}
        self.winner_chosen = False
        self.current_czar_selected_player = None
        self.choosing_playerName = None
        self.saved_scores = {}
        self.scores = {player: 0 for player in self.active_players}
        self.white_deck.reset()
        self.black_deck.reset()

        # Zufälliger Start-Czar: _next_czar geht einen Schritt weiter
        self.czarIndex = random.randrange(len(self.active_players)) - 1
        self._next_czar()
        self.current_black_card = self.black_deck.draw()
        self.fill_player_hands()
        self._set_timer(self.settings["timeToChooseWhiteCards"])

        return True, "Spiel gestartet"

    def _next_czar(self):
        """Nächster verbundener Spieler wird Czar, AFK-Spieler werden übersprungen"""
        count = len(self.active_players)
        for step in range(1, count + 1):
            index = (self.czarIndex + step) % count
            if self.is_status_connected(self.active_players[index]):
                break
        else:
            index = (self.czarIndex + 1) % count
        self.czarIndex = index
        self.czar = self.active_players[index]

    def fill_player_hands(self):
        for player in self.active_players:
            self._draw_hand(player, self.settings["maxWhiteCardsPerPlayer"])

    def timer_tick(self):
        if self.currentTimerSeconds < 0:
            return False, "Timer nicht aktiv (state={})".format(self.state)

        if self.paused:
            return True, "Pausiert"

        self.currentTimerSeconds -= 1
        if self.currentTimerSeconds > 0:
            return True, "Timer aktualisiert"

        if self.state == 'special_discard_round':
            self.next_round()
        elif self.state == 'choosing_cards':
            missing = [p for p in self._non_czar_players() if p not in self.submitted_white_cards]
            self._autosubmit(missing)
            self._enter_choosing_winner()
        elif self.state == 'choosing_winner':
            if self.winner_chosen:
                self.finalize_winner_choice()
            else:
                self._choose_random_winner()
        elif self.state == 'countdown_next_round':
            if self.settings["discardRoundActive"] and self.current_round != 0 \
                    and (self.current_round + 1) % self.settings["discardRoundInterval"] == 0:
                self._enter_discard_round()
            else:
                self.next_round()
        else:
            # Unbekannter Zustand -> Timer deaktivieren
            self._set_timer(-1)

        self.send_socket_game_update_for_all()
        return True, "Timer aktualisiert"

    def pause(self):
        if not self.is_game_started():
            return False, "Das Spiel wurde noch nicht gestartet"
        if self.state == 'choosing_winner' and self.winner_chosen:
            return False, "Das Spiel kann nach der Gewinnerauswahl nicht pausiert werden"
        if self.paused:
            return False, "Das Spiel ist bereits pausiert"
        self.paused = True
        return True, "Pausiert"

    def resume(self):
        """Gibt (ok, message, state_changed) zurück"""
        if not self.is_game_started():
            return False, "Das Spiel wurde noch nicht gestartet", False
        if not self.paused:
            return False, "Das Spiel ist nicht pausiert", False
        self.paused = False
        # Während der Pause können Spieler AFK gegangen sein
        changed = False
        if self.state == 'choosing_cards':
            changed = self._advance_if_all_submitted()
        elif self.state == 'special_discard_round':
            changed = self._advance_if_all_discarded()
        return True, "Fortgesetzt", changed

    # ---------- Karten abgeben ----------

    def submit_white_cards(self, playerName, white_cards_indicies):
        if self.paused:
            return False, "Spiel ist pausiert"
        if self.state != 'choosing_cards':
            return False, "Falsche Spielphase"
        if playerName in self.spectators:
            return False, "Zuschauer können nicht mitspielen"
        if playerName in self.pending_players:
            return False, "Du steigst in der nächsten Runde ein"
        if playerName not in self.active_players:
            return False, "Du bist kein aktiver Spieler"
        if playerName == self.czar:
            return False, "Der Czar darf nicht antworten"
        if playerName in self.submitted_white_cards:
            return False, "Du hast bereits abgegeben"

        num_blanks = self.current_black_card["num_blanks"]
        indices, error = parse_card_indices(white_cards_indicies, len(self.playerCards.get(playerName, [])))
        if error:
            return False, error
        if len(indices) != num_blanks:
            return False, f"Bitte wähle genau {num_blanks} Karte(n)"

        self.submitted_white_cards[playerName] = self._take_cards(playerName, indices)
        self._advance_if_all_submitted()
        return True, "Erfolgreich abgegeben"

    def _autosubmit(self, players):
        num_blanks = self.current_black_card["num_blanks"]
        for playerName in players:
            if playerName in self.submitted_white_cards or playerName not in self.active_players:
                continue
            hand = self._draw_hand(playerName, num_blanks)
            indices = random.sample(range(len(hand)), num_blanks)
            self.submitted_white_cards[playerName] = self._take_cards(playerName, indices)

    def _advance_if_all_submitted(self):
        """Wechselt zur Czar-Wahl, wenn alle verbundenen Spieler abgegeben haben. Gibt True bei Wechsel zurück."""
        if self.state != 'choosing_cards' or self.paused:
            return False

        non_czar = self._non_czar_players()
        missing = [p for p in non_czar if p not in self.submitted_white_cards]
        if missing:
            if any(self.is_status_connected(p) for p in missing):
                return False
            # Nur noch AFK-Spieler fehlen. Sind alle AFK, wird auf den Timer gewartet.
            if not any(self.is_status_connected(p) for p in non_czar):
                return False
            self._autosubmit(missing)

        self._enter_choosing_winner()
        return True

    def _enter_choosing_winner(self):
        self.state = 'choosing_winner'
        self.winner_chosen = False
        self.current_czar_selected_player = None
        self.choosing_playerName = None
        self.current_reactions = {}
        self._set_timer(self.settings["timeToChooseWinner"])

        # Bestimmte universelle Spieler reinfolge für die anzeige der eingesendeten Karten
        self.player_mapping = list(self.submitted_white_cards.keys())
        random.shuffle(self.player_mapping)

        # Ohne Czar (hat das Spiel verlassen) wird direkt zufällig gewählt
        if self.czar is None:
            self._choose_random_winner()

    # ---------- Gewinner ----------

    def _choose_random_winner(self):
        possible_winners = list(self.submitted_white_cards.keys())
        if possible_winners:
            self.choose_winner(random.choice(possible_winners), choosing_playerName=None)
        else:
            self.finalize_winner_choice()

    def choose_winner(self, winner_playerName, choosing_playerName=None):
        if self.paused and choosing_playerName:
            return False, "Spiel ist pausiert"
        if self.state != 'choosing_winner':
            return False, "Falsche Spielphase"
        if choosing_playerName and choosing_playerName != self.czar:
            return False, "Du bist nicht der Czar"
        if winner_playerName not in self.submitted_white_cards:
            return False, "Ungültiger Gewinner"

        self.current_czar_selected_player = winner_playerName
        self.choosing_playerName = choosing_playerName

        if choosing_playerName is None:
            # auto-chosen winner
            self.finalize_winner_choice()
            return True, "Gewinner gewählt"

        if not self.winner_chosen:
            self.winner_chosen = True
            self.broadcast_event_to_game("sound_event", "round_end_tick")
            self._set_timer(10)

        return True, "Gewinner gewählt"

    def finalize_winner_choice(self):
        winner = self.current_czar_selected_player

        if winner is not None and winner in self.submitted_white_cards:
            winning_cards = self.submitted_white_cards[winner]

            winning_reaction_points = 0
            for reactions in self.current_reactions.values():
                for to_player_index, points in reactions.items():
                    if self.player_mapping[to_player_index] == winner:
                        winning_reaction_points += points

            self.winning_white_cards = {
                'playerName': winner,
                'cards': winning_cards,
                'reaction_points': winning_reaction_points
            }
            self._add_point(winner)
            self.history.append({
                'round': self.current_round,
                'black_card': self.current_black_card,
                'submitted_cards': self.submitted_white_cards,
                'playerName': winner,
                'winning_cards': winning_cards,
                'reaction_points': winning_reaction_points,
                'czar': self.choosing_playerName # can be None if auto-chosen
            })
        else:
            self.winning_white_cards = {}

        for cards in self.submitted_white_cards.values():
            self.white_deck.discard(cards)

        self.current_czar_selected_player = None
        self.choosing_playerName = None
        self.winner_chosen = False
        self.submitted_white_cards = {}
        self.current_reactions = {}

        self.state = 'countdown_next_round'
        self._set_timer(self.settings["timeAfterWinnerChosen"])

    def submit_reaction(self, username, to_player_index, points):
        if self.state != 'choosing_winner':
            return False, "Reaktionen können nur während der Czar-Wahl-Phase abgegeben werden"
        if username not in self.active_players:
            return False, "Nur aktive Spieler können Reaktionen abgeben"
        if to_player_index < 0 or to_player_index >= len(self.player_mapping):
            return False, "Ungültiger Spielerindex für Reaktion"
        if points not in (-2, -1, 1, 2):
            return False, "Punkte für Reaktion müssen -2, -1, 1 oder 2 sein"
        if username == self.czar:
            return False, "Der Czar kann keine Reaktionen abgeben"
        if self.player_mapping[to_player_index] == username:
            return False, "Du kannst keine Reaktion auf deine eigene Antwort abgeben"

        self.current_reactions.setdefault(username, {})[to_player_index] = points
        return True, "Reaktion abgegeben"

    # ---------- Wegwerfrunde ----------

    def _enter_discard_round(self):
        self.state = 'special_discard_round'
        self.submitted_white_cards = {}
        self.fill_player_hands()
        self._set_timer(self.settings["discardTime"])

    def submit_discard_cards(self, playerName, white_cards_indicies):
        if self.paused:
            return False, "Spiel ist pausiert"
        if self.state != 'special_discard_round':
            return False, "Falsche Spielphase"
        if playerName in self.spectators:
            return False, "Zuschauer können nicht mitspielen"
        if playerName not in self.active_players:
            return False, "Du bist kein aktiver Spieler"
        if playerName in self.submitted_white_cards:
            return False, "Du hast bereits abgegeben"

        indices, error = parse_card_indices(white_cards_indicies, len(self.playerCards.get(playerName, [])))
        if error:
            return False, error
        if len(indices) > self.settings["discardMaxCards"]:
            return False, "Zu viele Karten zum Abwerfen ausgewählt"

        cards = self._take_cards(playerName, indices)
        self.white_deck.discard(cards)
        self.submitted_white_cards[playerName] = cards

        self._advance_if_all_discarded()
        return True, "Karten abgeworfen"

    def _advance_if_all_discarded(self):
        if self.state != 'special_discard_round' or self.paused:
            return False
        connected = [p for p in self.active_players if self.is_status_connected(p)]
        if not connected or any(p not in self.submitted_white_cards for p in connected):
            return False
        self.next_round()
        return True

    # ---------- Rundenwechsel / Ende ----------

    def next_round(self):
        if self.state != 'countdown_next_round' and self.state != 'special_discard_round':
            return False, "Falsche Spielphase"

        # check if max rounds reached
        if (self.current_round + 1) >= self.settings["maxRounds"]:
            self.end_game()
            return True, "Spiel beendet: Maximale Runden erreicht"

        # check if player reached score to win
        for player, score in self.scores.items():
            if score >= self.settings["maxPointsToWin"]:
                self.end_game()
                return True, "Spiel beendet: Spieler {} hat gewonnen".format(player)

        # Spieler, die während des Spiels beigetreten sind, steigen jetzt ein
        self._promote_pending_players()

        # check if not enough players
        if len(self.active_players) < 3:
            self.end_game()
            return True, "Spiel beendet: Nicht genügend Spieler"

        self.broadcast_event_to_game("sound_event", "round_start")

        if self.current_black_card:
            self.black_deck.discard([self.current_black_card])

        self.current_round += 1
        self.submitted_white_cards = {}
        self.winning_white_cards = {}
        self.player_mapping = []
        self.current_reactions = {}
        self._next_czar()
        self.current_black_card = self.black_deck.draw()
        self.fill_player_hands()
        self.state = 'choosing_cards'
        self._set_timer(self.settings["timeToChooseWhiteCards"])
        self.send_socket_game_update_for_all()
        return True, "Neue Runde gestartet"

    def end_game(self):
        self.broadcast_event_to_game("sound_event", "game_finished")
        self._promote_pending_players()
        self.state = 'game_ended'
        self.paused = False
        self._set_timer(-1)
        self.czar = None
        self.czarIndex = 0
        self.winner_chosen = False
        self.current_czar_selected_player = None
        self.choosing_playerName = None
        self.playerCards = {}
        self.current_black_card = {}
        self.winning_white_cards = {}
        self.submitted_white_cards = {}
        self.player_mapping = []
        self.current_reactions = {}
        self.returned_to_lobby = []

    def user_return_to_lobby(self, playerName):
        if self.state != 'game_ended':
            return False, "Das Spiel ist noch nicht beendet"
        if not self.is_member(playerName):
            return False, "Du bist kein Spieler oder Zuschauer in diesem Spiel"
        if playerName in self.returned_to_lobby:
            return False, "Du bist bereits zur Lobby zurückgekehrt"

        self.returned_to_lobby.append(playerName)
        self._check_all_returned_to_lobby()
        return True, "Zurück zur Lobby"

    def _check_all_returned_to_lobby(self):
        """Lobby zurücksetzen, sobald alle verbundenen Mitglieder zurückgekehrt sind"""
        if self.state != 'game_ended' or not self.returned_to_lobby:
            return False
        connected = [m for m in self.members() if self.is_status_connected(m)]
        if any(m not in self.returned_to_lobby for m in connected):
            return False
        self.reset_to_lobby()
        return True

    def reset_to_lobby(self):
        self._promote_pending_players()
        self.returned_to_lobby = []
        self.state = 'lobby'
        self.current_round = 0
        self.playerCards = {}
        self.current_black_card = {}
        self.winning_white_cards = {}
        self.submitted_white_cards = {}
        self.player_mapping = []
        self.current_reactions = {}
        self.scores = {}
        self.saved_scores = {}
        self.czarIndex = 0
        self.czar = None
        self._set_timer(0)
        self.paused = False
        self.winner_chosen = False
        self.current_czar_selected_player = None
        self.choosing_playerName = None
