from questions import CARDS_QUESTIONS
from answers import CARDS_ANSWERS
import uuid
import random

class Game:
    def __init__(self, ownerName):
        self.game_id = str(uuid.uuid4())
        self.owner = ownerName      # Owner's player name
        self.active_players = [ownerName]         # List of player objects or IDs
        self.player_status = {ownerName: 'active'}   # playerName: 'active', 'disconnected', etc.
        self.spectators = []      # List of spectator objects


        # Game variables
        self.history = []          # list of past rounds
        self.current_round = 0     # current round number
        self.playerCards = {}   # playerName: list of white cards
        self.current_black_card = {} # current black card -> card_text: str, num_blanks: int
        self.winning_white_cards = []  # list of winning white cards in current round
        self.submitted_white_cards = {}  # playerName: [white_card(s)]
        self.scores = {}           # playerName: score
        self.czarIndex = 0      # index of current czar in active_players -> random set-value at start
        self.czar = None           # playerName of current czar
        self.state = 'lobby'  # 'lobby', 'choosing_cards', 'choosing_winner', 'countdown_next_round', 'game_ended'
        self.currentTimerTotalSeconds = 0  # total seconds for current timer
        self.currentTimerSeconds = 0      # remaining seconds for current timer
        self.paused = False # whether the game is paused (owner can pause during choosing phases)

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
            "maxPlayers": 100
        }
    
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
            "winning_white_cards": self.winning_white_cards,
            "submitted_white_cards": self.submitted_white_cards,
            "scores": self.scores,
            "czarIndex": self.czarIndex,
            "czar": self.czar,
            "state": self.state,
            "currentTimerTotalSeconds": self.currentTimerTotalSeconds,
            "currentTimerSeconds": self.currentTimerSeconds,
            "paused": self.paused,
            "settings": self.settings
        }

    def toogle_pause(self):
        self.paused = not self.paused

    def timer_tick(self):
        if self.currentTimerSeconds < 0:
            return False
        
        if not self.paused:
            self.currentTimerSeconds -= 1
        
        if self.currentTimerSeconds == 0:
            if self.state == 'choosing_cards':
                self.autosubmit_white_cards()
            if self.state == 'choosing_winner':
                # auto choose random winner
                possible_winners = list(self.submitted_white_cards.keys())
                if possible_winners:
                    chosen_winner = random.choice(possible_winners)
                    self.choose_winner(chosen_winner, choosing_playerName=None)
            if self.state == 'countdown_next_round':
                self.next_round()

        return True

    def is_game_started(self):
        return self.state != 'lobby'

    def add_player(self, playerName, isSpectator):
        if not playerName:
            return False
        if len(self.active_players) >= self.settings["maxPlayers"] and not isSpectator:
            return False
        if playerName in self.active_players:
            return False
        if playerName in self.spectators:
            return False

        if isSpectator:
            self.spectators.append(playerName)
        else:
            self.active_players.append(playerName)
        
        self.player_status[playerName] = 'active'

        return True
    
    def mark_player_connection_status(self, playerName, status):
        if playerName in self.player_status:
            self.player_status[playerName] = status
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
                self.owner = self.active_players[0]
            elif len(self.spectators) > 0:
                self.owner = self.spectators[0]
            else:
                self.owner = None # Game can be deleted because no players/spectators are left

        if len(self.active_players) < 3 and self.is_game_started():
            self.end_game()

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

    def autosubmit_white_cards(self):
        for playerName in self.active_players:
            if playerName != self.czar and playerName not in self.submitted_white_cards:
                # choose random white card(s)
                num_cards_needed = self.current_black_card["num_blanks"]
                player_hand = self.playerCards[playerName]
                chosen_cards = random.sample(player_hand, num_cards_needed)
                self.submit_white_card(playerName, chosen_cards)

    def submit_white_card(self, playerName, white_cards):
        if self.state != 'choosing_cards':
            return False
        if playerName == self.czar:
            return False
        if playerName not in self.active_players:
            return False
        if playerName in self.submitted_white_cards:
            return False
    
        self.submitted_white_cards[playerName] = white_cards
        # remove white cards from player's hand
        playerCards = self.playerCards.get(playerName, [])
        for card in white_cards:
            if card in playerCards:
                playerCards.remove(card)
        self.playerCards[playerName] = playerCards

        # if everyone has submitted, move to choosing_winner
        if len(self.submitted_white_cards) >= len(self.active_players) - 1:
            self.state = 'choosing_winner'
            self.currentTimerTotalSeconds = self.settings["timeToChooseWinner"]
            self.currentTimerSeconds = self.currentTimerTotalSeconds

        return True

    def choose_winner(self, winner_playerName, choosing_playerName=None):
        if self.state != 'choosing_winner':
            return False
        if choosing_playerName != self.czar and choosing_playerName != None:
            return False
        if winner_playerName not in self.submitted_white_cards:
            return False

        winning_cards = self.submitted_white_cards[winner_playerName]
        self.winning_white_cards = winning_cards
        self.scores[winner_playerName] += 1
        self.history.append({
            'round': self.current_round,
            'black_card': self.current_black_card,
            'submitted_cards': self.submitted_white_cards,
            'winner': winner_playerName,
            'winning_cards': winning_cards,
            'czar': choosing_playerName # can be None if auto-chosen
        })

        self.state = 'countdown_next_round'
        self.currentTimerTotalSeconds = self.settings["timeAfterWinnerChosen"]
        self.currentTimerSeconds = self.currentTimerTotalSeconds
        

    def next_round(self):
        if self.state != 'countdown_next_round':
            return False
        
        # check if max rounds reached
        if (self.current_round+1) >= self.settings["maxRounds"]:
            self.end_game()
            return True
        
        # check if player reached score to win
        for player, score in self.scores.items():
            if score >= self.settings["maxPointsToWin"]:
                self.end_game()
                return True
            
        # check if not enough players
        if len(self.active_players) < 3:
            self.end_game()
            return True

        self.current_round += 1
        self.submitted_white_cards = {}
        self.winning_white_cards = []
        self.czarIndex = (self.czarIndex + 1) % len(self.active_players)
        self.czar = self.active_players[self.czarIndex % len(self.active_players)]
        self.current_black_card = random.choice(CARDS_QUESTIONS)
        self.fill_player_hands()
        self.state = 'choosing_cards'
        self.currentTimerTotalSeconds = self.settings["timeToChooseWhiteCards"]
        self.currentTimerSeconds = self.currentTimerTotalSeconds

    def end_game(self):
        self.state = 'game_ended'
        self.currentTimerTotalSeconds = -1
        self.currentTimerSeconds = -1
        