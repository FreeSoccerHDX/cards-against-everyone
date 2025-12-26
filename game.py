from questions import CARDS_QUESTIONS
from answers import CARDS_ANSWERS
import uuid
import random

class Game:
    def __init__(self, ownerName):
        self.game_id = str(uuid.uuid4())
        self.owner = ownerName      # Owner's player name
        self.active_players = [ownerName]         # List of player objects or IDs
        self.spectators = []      # List of spectator objects
        self.max_players = 100  # Maximum number of players

        # Game variables
        self.history = []          # list of past rounds
        self.current_round = 0     # current round number
        self.playerCards = {}   # player_id: list of white cards
        self.current_black_card = "" # current black card -> string
        self.winning_white_cards = []  # list of winning white cards in current round
        self.submitted_white_cards = {}  # player_id: [white_card(s)]
        self.scores = {}           # player_id: score
        self.czarIndex = 0      # index of current czar in active_players -> random set at start
        self.czar = None           # player_id of current czar
        self.state = 'lobby'  # 'lobby', 'choosing_cards', 'choosing_winner', 'countdown_next_round', 'game_ended'
        self.currentTimerTotalSeconds = 0  # total seconds for current timer
        self.currentTimerSeconds = 0      # remaining seconds for current timer

        # Game Settings
        self.settings = {    
            "gameName": ownerName + "'s Game",
            "publicVisible": True,
            "password": "",
            "maxWhiteCardsPerPlayer": 7,
            "maxPointsToWin": 5,
            "maxRounds": 25,
            "timeToChooseWhiteCards": 60,
            "timeToChooseWinner": 60,
            "timeAfterWinnerChosen": 15,
        }
    
    def timer_tick(self):
        if self.currentTimerSeconds >= 0:
            self.currentTimerSeconds -= 1
            return True
        return False

    def is_game_started(self):
        return self.state != 'lobby'

    def add_player(self, playerName, isSpectator):
        if not playerName:
            return False
        if len(self.active_players) >= self.max_players:
            return False
        if playerName in self.active_players:
            return False
        if playerName in self.spectators:
            return False

        if isSpectator:
            self.spectators.append(playerName)
        else:
            self.active_players.append(playerName)
        return True

    def remove_player(self, playerName):
        isSpectator = playerName in self.spectators
        isPlayer = playerName in self.active_players

        if not isSpectator and not isPlayer:
            return False

        if isSpectator:
            self.spectators.remove(playerName)

        if isPlayer:
            self.active_players.remove(playerName)
            self.scores.pop(playerName, None)
            self.submitted_white_cards.pop(playerName, None)
                
            if self.czar == playerName: # only player
                self.czar = None
                if len(self.active_players) > 0:
                    self.next_round()

        if self.owner == playerName: # spectator or player
            self.owner = None
            if len(self.active_players) > 0:
                self.owner = self.active_players[0]
            elif len(self.spectators) > 0:
                self.owner = self.spectators[0]
            else:
                self.owner = None # Game can be deleted because no players/spectators are left

        return True

    def start_game(self):
        if self.is_game_started():
            return False
        if len(self.active_players) < 3:
            return False

        self.state = 'choosing_cards'
        self.current_round = 0
        self.scores = {}
        self.submitted_white_cards = {}
        self.history = []
        self.playerCards = {}
        self.winning_white_cards = []
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

    def next_round(self):
        pass

    def submit_white_card(self, player, white_card):
        pass

    def choose_winner(self, winner_player):
        pass

    def end_game(self):
        pass

    def get_winner(self):
        pass