from questions import CARDS_QUESTIONS
from answers import CARDS_ANSWERS
import uuid
import random

class Game:
    def __init__(self, socketio, global_player_data, ownerName, gameName, isPublicVisible=True, password=""):
        self.socketio = socketio
        self.global_player_data = global_player_data
        self.game_id = str(uuid.uuid4())
        self.owner = ownerName      # Owner's player name
        self.active_players = [ownerName]         # List of player objects or IDs
        self.player_status = {ownerName: 'connected'}   # playerName: 'connected', 'disconnected', etc.
        self.spectators = []      # List of spectator names


        # Game variables
        self.history = []          # list of past rounds
        self.current_round = 0     # current round number
        self.playerCards = {}   # playerName: list of white cards
        self.current_black_card = {} # current black card -> card_text: str, num_blanks: int
        self.winning_white_cards = {}  # list of winning white cards in current round
        self.submitted_white_cards = {}  # playerName: [white_card(s)]
        self.player_mapping = []    # List of playerNames random order for displaying submitted cards
        self.scores = {}           # playerName: score
        self.czarIndex = 0      # index of current czar in active_players -> random set-value at start
        self.czar = None           # playerName of current czar
        self.state = 'lobby'  # 'lobby', 'choosing_cards', 'choosing_winner', 'countdown_next_round', 'game_ended'
        self.currentTimerTotalSeconds = 0  # total seconds for current timer
        self.currentTimerSeconds = 0      # remaining seconds for current timer
        self.paused = False # whether the game is paused (owner can pause during choosing phases)
        self.winner_choosen = False
        self.current_czar_selected_player = None   
        self.choosing_playerName = None

        # Game Settings
        self.settings = {    
            "gameName": gameName if gameName else ownerName + "'s Game",
            "publicVisible": isPublicVisible,
            "publicVisibleDuringGame": False,
            "password": password,
            "maxWhiteCardsPerPlayer": 7,
            "maxPointsToWin": 5,
            "maxRounds": 25,
            "timeToChooseWhiteCards": 60,
            "timeToChooseWinner": 60,
            "timeAfterWinnerChosen": 15,
            "maxPlayers": 10
        }

    def updateSettings(self, newSettings):
        for key, value in newSettings.items():
            if key in self.settings and value is not None:
                self.settings[key] = value
    
    def send_socket_game_update_for_all(self, channel="game_state_update", include_history=False):
        for player in self.active_players + self.spectators:
            self.socketio.emit(channel, self.get_socket_game_data(
                    include_player_cards=False,
                    current_player_cards=player,
                    include_history=include_history
                )
            , room=self.global_player_data[player]['sid'])


    def get_socket_game_data(self, include_player_cards=False, current_player_cards:str=None, include_history=False):
        return {
            "game_id": self.game_id,
            "owner": self.owner,
            "active_players": self.active_players,
            "player_status": self.player_status,
            "spectators": self.spectators,
            "history": self.history if include_history else [],
            "current_round": self.current_round,
            "playerCards": self.playerCards if include_player_cards else {},
            "currentPlayerCards": self.playerCards.get(current_player_cards, []) if current_player_cards else [],
            "current_black_card": self.current_black_card,
            "player_mapping": self.player_mapping,
            "winning_white_cards": self.winning_white_cards,
            "submitted_white_cards": self.submitted_white_cards,
            "scores": self.scores,
            "czarIndex": self.czarIndex,
            "czar": self.czar,
            "state": self.state,
            "currentTimerTotalSeconds": self.currentTimerTotalSeconds,
            "currentTimerSeconds": self.currentTimerSeconds,
            "paused": self.paused,
            "winner_choosen": self.winner_choosen,
            "current_czar_selected_player": self.current_czar_selected_player if self.czar == current_player_cards else None,
            "settings": self.settings
        }
    
    def toggle_role(self, playerName):
        if self.is_game_started():
            return False, "Spiel bereits gestartet"
        
        if playerName in self.spectators:
            # switch to player
            if len(self.active_players) >= self.settings["maxPlayers"]:
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

    def toogle_pause(self):
        self.paused = not self.paused

    def timer_tick(self):
        if self.currentTimerSeconds < 0:
            return False, "Timer nicht aktiv (state={})".format(self.state)
        
        if not self.paused:
            self.currentTimerSeconds -= 1
        
        if self.currentTimerSeconds == 0:
            if self.state == 'choosing_cards':
                self.autosubmit_white_cards(ignoreConnection=True)
            elif self.state == 'choosing_winner':
                if self.winner_choosen:
                    self.finalize_winner_choice()
                    self.winner_choosen = False
                    self.current_czar_selected_player = None
                    self.choosing_playerName = None
                else:
                    # auto choose random winner
                    possible_winners = list(self.submitted_white_cards.keys())
                    if possible_winners:
                        chosen_winner = random.choice(possible_winners)
                        self.choose_winner(chosen_winner, choosing_playerName=None)

            elif self.state == 'countdown_next_round':
                success,error = self.next_round()
                if not success:
                    print("Error moving to next round:", error)
            self.send_socket_game_update_for_all(include_history=True)
        return True,"Timer aktualisiert"

    def is_game_started(self):
        return self.state != 'lobby' and self.state != 'game_ended'

    def add_player(self, playerName, isSpectator):
        if not playerName:
            return False, "Ungültiger Spielername"
        if len(self.active_players) >= self.settings["maxPlayers"] and not isSpectator:
            return False, "Maximale Spieleranzahl erreicht"
        if playerName in self.active_players and self.is_status_connected(playerName):
            return False, "Spieler bereits im Spiel"
        if playerName in self.spectators and self.is_status_connected(playerName):
            return False, "Spieler bereits Zuschauer"

        if isSpectator:
            if not playerName in self.spectators:
                self.spectators.append(playerName)
        else:
            if not playerName in self.active_players:
                self.active_players.append(playerName)
        
        self.player_status[playerName] = 'connected'

        return True, "Spieler hinzugefügt"
    
    def mark_player_connection_status(self, playerName, status):
        if playerName in self.player_status:
            self.player_status[playerName] = status

            self.socketio.emit('player_status_changed', {
                'username': playerName,
                'status': status
            }, room=self.game_id)

            return True
            
        return False

    def remove_player(self, playerName):
        isSpectator = playerName in self.spectators
        isPlayer = playerName in self.active_players

        self.player_status.pop(playerName, None)

        if not isSpectator and not isPlayer:
            return False

        if isSpectator:
            self.spectators.remove(playerName)

        if isPlayer:
            self.active_players.remove(playerName)
            self.scores.pop(playerName, None)
            self.submitted_white_cards.pop(playerName, None)
            
            if self.is_game_started(): # only if game started
                if self.czar == playerName: # only player
                    self.czarIndex -= 1
                    # do nothing and wait for next round to assign new czar
                    

        if self.owner == playerName: # possible for spectator or player
            self.owner = None
            if len(self.active_players) > 0:
                for player in self.active_players:
                    if self.is_status_connected(player):
                        self.owner = player
                        break
            elif len(self.spectators) > 0:
                for spectator in self.spectators:
                    if self.is_status_connected(spectator):
                        self.owner = spectator
                        break
            else:
                self.owner = None # Game can be deleted because no players/spectators are left

        if len(self.active_players) < 3 and self.is_game_started():
            self.end_game()

        return True

    def is_status_connected(self, playerName):
        return self.player_status.get(playerName) == 'connected'

    def start_game(self):
        if self.is_game_started():
            return False
        if len(self.active_players) < 3:
            return False

        self.state = 'choosing_cards'
        self.current_round = 0
        self.scores = {}
        self.submitted_white_cards = {}
        self.player_mapping = []
        self.history = []
        self.playerCards = {}
        self.winning_white_cards = {}
        self.scores = {player: 0 for player in self.active_players}
        self.czarIndex = random.randint(0, len(self.active_players) - 1)
        self.czar = self.active_players[self.czarIndex % len(self.active_players)]
        self.currentTimerTotalSeconds = self.settings["timeToChooseWhiteCards"]
        self.currentTimerSeconds = self.currentTimerTotalSeconds
        self.current_black_card = random.choice(CARDS_QUESTIONS)
        self.fill_player_hands()

        return True

    def fill_player_hands(self):
        for player in self.active_players:
            if player not in self.playerCards:
                self.playerCards[player] = []
            while len(self.playerCards[player]) < self.settings["maxWhiteCardsPerPlayer"]:
                new_card = random.choice(CARDS_ANSWERS)
                self.playerCards[player].append(new_card)

    def autosubmit_white_cards(self, ignoreConnection=False):
        for playerName in self.active_players:
            if playerName != self.czar and playerName not in self.submitted_white_cards:
                if ignoreConnection or self.player_status.get(playerName, 'connected') != 'connected':    
                    # choose random white card(s)
                    num_cards_needed = self.current_black_card["num_blanks"]
                    player_hand = self.playerCards[playerName]
                    chosen_cards = random.sample(player_hand, num_cards_needed)
                    chosen_indices = [player_hand.index(card) for card in chosen_cards]
                    self.submit_white_cards(playerName, chosen_indices)

    def submit_white_cards(self, playerName, white_cards_indicies):
        if self.paused:
            return False,"Spiel ist pausiert"
        if self.state != 'choosing_cards':
            return False,"Falsche Spielphase"
        if playerName in self.spectators:
            return False,"Zuschauer können nicht mitspielen"
        if playerName == self.czar:
            return False,"Der Czar darf nicht antworten"
        if playerName not in self.active_players:
            return False,"Du bist kein aktiver Spieler"
        if playerName in self.submitted_white_cards:
            return False,"Du hast bereits abgegeben"

        playerCards = self.playerCards.get(playerName, [])
        submitting_cards = []
        for card_indicies in white_cards_indicies:
            if card_indicies > len(playerCards)-1 or card_indicies < 0:
                return False,"Karte(n) nicht in deinem Blatt"
            submitting_cards.append(playerCards[card_indicies])

        self.submitted_white_cards[playerName] = submitting_cards

        # remove white cards from player's hand
        for submit_card in submitting_cards:
            playerCards.remove(submit_card)

        # if everyone has submitted, move to choosing_winner
        if len(self.submitted_white_cards) >= len(self.active_players) - 1:
            self.state = 'choosing_winner'
            self.currentTimerTotalSeconds = self.settings["timeToChooseWinner"]
            self.currentTimerSeconds = self.currentTimerTotalSeconds

            # Bestimmte universelle Spieler reinfolge für die anzeige der eingesendeten Karten
            self.player_mapping = list(self.submitted_white_cards.keys())
            random.shuffle(self.player_mapping)

        return True,"Erfiolgreich abgegeben"

    def finalize_winner_choice(self):
        winning_cards = self.submitted_white_cards[self.current_czar_selected_player]
        self.winning_white_cards = {
            'playerName': self.current_czar_selected_player,
            'cards': winning_cards
        }
        self.scores[self.current_czar_selected_player] += 1
        self.history.append({
            'round': self.current_round,
            'black_card': self.current_black_card,
            'submitted_cards': self.submitted_white_cards,
            'playerName': self.current_czar_selected_player,
            'winning_cards': winning_cards,
            'czar': self.choosing_playerName # can be None if auto-chosen
        })

        self.current_czar_selected_player = None
        self.choosing_playerName = None
        self.winner_choosen = False
        self.submitted_white_cards = {}

        self.state = 'countdown_next_round'
        self.currentTimerTotalSeconds = self.settings["timeAfterWinnerChosen"]
        self.currentTimerSeconds = self.currentTimerTotalSeconds


    def choose_winner(self, winner_playerName, choosing_playerName=None):
        if self.paused:
            return False,"Spiel ist pausiert"
        if self.state != 'choosing_winner':
            return False,"Falsche Spielphase"
        if choosing_playerName and choosing_playerName != self.czar:
            return False,"Du bist nicht der Czar"
        if winner_playerName not in self.submitted_white_cards:
            return False,"Ungültiger Gewinner"

        self.current_czar_selected_player = winner_playerName
        self.choosing_playerName = choosing_playerName

        if not self.winner_choosen:
            self.winner_choosen = True
            self.currentTimerTotalSeconds = 10
            self.currentTimerSeconds = 10

        if(self.choosing_playerName is None):
            # auto-chosen winner
            self.finalize_winner_choice()
            return True,"Gewinner gewählt"

        return True,"Gewinner gewählt"

    def is_pending_player(self, playerName):
        if not playerName:
            return False
        # Check if player is active/spectator and connection status is not connected
        if playerName in self.active_players or playerName in self.spectators:
            return not self.is_status_connected(playerName)


    def next_round(self):
        if self.state != 'countdown_next_round':
            return False,"Falsche Spielphase"
        
        # check if max rounds reached
        if (self.current_round+1) >= self.settings["maxRounds"]:
            self.end_game()
            return True,"Spiel beendet: Maximale Runden erreicht"
        
        # check if player reached score to win
        for player, score in self.scores.items():
            if score >= self.settings["maxPointsToWin"]:
                self.end_game()
                return True,"Spiel beendet: Spieler {} hat gewonnen".format(player)
            
        # check if not enough players
        if len(self.active_players) < 3:
            self.end_game()
            return True,"Spiel beendet: Nicht genügend Spieler"

        self.current_round += 1
        self.submitted_white_cards = {}
        self.winning_white_cards = {}
        self.player_mapping = []
        self.czarIndex = (self.czarIndex + 1) % len(self.active_players)
        self.czar = self.active_players[self.czarIndex % len(self.active_players)]
        self.current_black_card = random.choice(CARDS_QUESTIONS)
        self.fill_player_hands()
        self.state = 'choosing_cards'
        self.currentTimerTotalSeconds = self.settings["timeToChooseWhiteCards"]
        self.currentTimerSeconds = self.currentTimerTotalSeconds
        return True,"Neue Runde gestartet"

    def end_game(self):
        self.state = 'game_ended'
        self.currentTimerTotalSeconds = -1
        self.currentTimerSeconds = -1

    def reset_to_lobby(self):
        self.state = 'lobby'
        self.current_round = 0
        self.playerCards = {}
        self.current_black_card = {}
        self.winning_white_cards = {}
        self.submitted_white_cards = {}
        self.player_mapping = []
        self.scores = {}
        self.czarIndex = 0
        self.czar = None
        self.currentTimerTotalSeconds = 0
        self.currentTimerSeconds = 0
        self.paused = False
        