from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import uuid
import time
import random
import eventlet
from questions import CARDS_QUESTIONS
from answers import CARDS_ANSWERS

app = Flask(__name__)
app.config['SECRET_KEY'] = 'cards-against-everyone-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

# Datenstrukturen
users = {}  # {username: {sid: str, last_seen: float, game_id: str}}
games = {}  # {game_id: {name: str, creator: str, players: [], settings: {}, is_public: bool, password: str}}
disconnect_timers = {}  # {username: Timer}

def cleanup_user(username):
    """Entfernt Benutzer nach 30 Sekunden Inaktivität"""
    if username in users:
        game_id = users[username].get('game_id')
        if game_id and game_id in games:
            # Entferne Spieler aus dem Spiel
            if username in games[game_id]['players']:
                games[game_id]['players'].remove(username)
                
                # Wenn Ersteller weg ist, neuen Ersteller bestimmen
                if games[game_id]['creator'] == username and games[game_id]['players']:
                    games[game_id]['creator'] = games[game_id]['players'][0]
                
                # Spiel löschen wenn leer
                if not games[game_id]['players']:
                    # Stoppe alle Timer wenn das Spiel gelöscht wird
                    if games[game_id].get('game_state'):
                        state = games[game_id]['game_state']
                        
                        # Stoppe Round Timer
                        if state.get('round_timer'):
                            try:
                                eventlet.kill(state['round_timer'])
                            except:
                                pass
                            state['round_timer'] = None
                        
                        # Stoppe Timer Sync Task
                        if state.get('timer_sync_task'):
                            try:
                                eventlet.kill(state['timer_sync_task'])
                            except:
                                pass
                            state['timer_sync_task'] = None
                    
                    del games[game_id]
                else:
                    # Informiere andere Spieler
                    socketio.emit('player_left', {
                        'username': username,
                        'players': games[game_id]['players'],
                        'creator': games[game_id]['creator']
                    }, room=game_id)
        
        del users[username]
        if username in disconnect_timers:
            del disconnect_timers[username]

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    print(f'Client connected: {request.sid}')

@socketio.on('disconnect')
def handle_disconnect():
    print(f'Client disconnected: {request.sid}')
    # Finde Benutzer mit dieser SID
    username = None
    for user, data in users.items():
        if data['sid'] == request.sid:
            username = user
            break
    
    if username:
        # Starte 30-Sekunden-Timer mit eventlet
        if username in disconnect_timers:
            try:
                eventlet.kill(disconnect_timers[username])
            except:
                pass
        
        timer = eventlet.spawn_after(30.0, cleanup_user, username)
        disconnect_timers[username] = timer

@socketio.on('set_username')
def handle_set_username(data):
    username = data.get('username', '').strip()
    
    if not username:
        emit('username_error', {'message': 'Bitte gib einen Namen ein'})
        return
    
    # Prüfe ob Name bereits existiert
    if username in users:
        # Wenn es der gleiche Benutzer ist (Reconnect)
        if users[username]['sid'] == request.sid:
            emit('username_set', {'username': username})
            return
        
        # Name bereits vergeben
        emit('username_error', {'message': 'Dieser Name ist bereits vergeben'})
        return
    
    # Registriere Benutzer
    users[username] = {
        'sid': request.sid,
        'last_seen': time.time(),
        'game_id': None
    }
    
    # Lösche eventuellen Timer
    if username in disconnect_timers:
        try:
            eventlet.kill(disconnect_timers[username])
        except:
            pass
        del disconnect_timers[username]
    
    emit('username_set', {'username': username})
    print(f'Username set: {username}')

@socketio.on('reconnect_user')
def handle_reconnect(data):
    username = data.get('username', '').strip()
    
    if username in users:
        # Aktualisiere SID
        users[username]['sid'] = request.sid
        users[username]['last_seen'] = time.time()
        
        # Lösche Timer
        if username in disconnect_timers:
            try:
                eventlet.kill(disconnect_timers[username])
            except:
                pass
            del disconnect_timers[username]
        
        game_id = users[username].get('game_id')
        if game_id and game_id in games:
            # Trete Raum wieder bei
            join_room(game_id)
            emit('reconnected', {
                'username': username,
                'game_id': game_id,
                'game': games[game_id]
            })
        else:
            emit('reconnected', {'username': username})
    else:
        emit('username_error', {'message': 'Sitzung abgelaufen, bitte Namen neu eingeben'})

@socketio.on('create_game')
def handle_create_game(data):
    username = None
    for user, user_data in users.items():
        if user_data['sid'] == request.sid:
            username = user
            break
    
    if not username:
        emit('error', {'message': 'Nicht angemeldet'})
        return
    
    game_name = data.get('name', 'Neues Spiel').strip()
    is_public = data.get('is_public', True)
    password = data.get('password', '').strip()
    
    game_id = str(uuid.uuid4())
    
    games[game_id] = {
        'id': game_id,
        'name': game_name,
        'creator': username,
        'players': [username],
        'is_public': is_public,
        'password': password,
        'settings': {
            'max_cards': 7,
            'win_score': 10,
            'answer_time': 60,  # Sekunden für automatische Abgabe
            'round_delay': 5,  # Sekunden zwischen Runden
            'czar_time': 30  # Sekunden für Card Czar Voting
        },
        'started': False,
        'game_state': None  # Wird gesetzt wenn Spiel startet
    }
    
    users[username]['game_id'] = game_id
    join_room(game_id)
    
    emit('game_created', {'game_id': game_id, 'game': games[game_id]})
    # Aktualisiere Lobby für alle
    socketio.emit('lobby_update', {'games': get_public_games()})

@socketio.on('get_public_games')
def handle_get_public_games():
    emit('public_games', {'games': get_public_games()})

@socketio.on('get_game_info')
def handle_get_game_info(data):
    game_id = data.get('game_id')
    if game_id not in games:
        emit('game_info_error', {'message': 'Spiel nicht gefunden'})
        return
    
    game = games[game_id]
    emit('game_info', {
        'game_id': game_id,
        'name': game['name'],
        'has_password': bool(game['password']),
        'started': game['started']
    })

def get_public_games():
    """Gibt alle öffentlichen Spiele zurück"""
    public_games = []
    for game_id, game in games.items():
        if game['is_public'] and not game['started']:
            public_games.append({
                'id': game_id,
                'name': game['name'],
                'players': len(game['players']),
                'has_password': bool(game['password'])
            })
    return public_games

@socketio.on('join_game')
def handle_join_game(data):
    username = None
    for user, user_data in users.items():
        if user_data['sid'] == request.sid:
            username = user
            break
    
    if not username:
        emit('error', {'message': 'Nicht angemeldet'})
        return
    
    game_id = data.get('game_id')
    password = data.get('password', '')
    
    if game_id not in games:
        emit('error', {'message': 'Spiel nicht gefunden'})
        return
    
    game = games[game_id]
    
    # Prüfe Passwort
    if game['password'] and game['password'] != password:
        emit('error', {'message': 'Falsches Passwort'})
        return
    
    # Prüfe ob Spiel bereits gestartet
    if game['started']:
        emit('error', {'message': 'Spiel bereits gestartet'})
        return
    
    # Füge Spieler hinzu
    if username not in game['players']:
        game['players'].append(username)
    
    users[username]['game_id'] = game_id
    join_room(game_id)
    
    emit('game_joined', {'game_id': game_id, 'game': game})
    
    # Informiere andere Spieler
    emit('player_joined', {
        'username': username,
        'players': game['players']
    }, room=game_id, include_self=False)
    
    # Aktualisiere Lobby
    socketio.emit('lobby_update', {'games': get_public_games()})

@socketio.on('leave_game')
def handle_leave_game():
    username = None
    for user, user_data in users.items():
        if user_data['sid'] == request.sid:
            username = user
            break
    
    if not username:
        return
    
    game_id = users[username].get('game_id')
    if not game_id or game_id not in games:
        return
    
    game = games[game_id]
    
    # Entferne Spieler
    if username in game['players']:
        game['players'].remove(username)
    
    # Wenn Ersteller weg ist, neuen Ersteller bestimmen
    if game['creator'] == username and game['players']:
        game['creator'] = game['players'][0]
    
    users[username]['game_id'] = None
    leave_room(game_id)
    
    # Spiel löschen wenn leer
    if not game['players']:
        # Stoppe alle Timer wenn das Spiel gelöscht wird
        if game.get('game_state'):
            state = game['game_state']
            
            # Stoppe Round Timer
            if state.get('round_timer'):
                try:
                    eventlet.kill(state['round_timer'])
                except:
                    pass
                state['round_timer'] = None
            
            # Stoppe Timer Sync Task
            if state.get('timer_sync_task'):
                try:
                    eventlet.kill(state['timer_sync_task'])
                except:
                    pass
                state['timer_sync_task'] = None
        
        del games[game_id]
    else:
        # Informiere andere Spieler
        emit('player_left', {
            'username': username,
            'players': game['players'],
            'creator': game['creator']
        }, room=game_id)
    
    emit('left_game', {})
    # Aktualisiere Lobby
    socketio.emit('lobby_update', {'games': get_public_games()})

@socketio.on('update_settings')
def handle_update_settings(data):
    username = None
    for user, user_data in users.items():
        if user_data['sid'] == request.sid:
            username = user
            break
    
    if not username:
        return
    
    game_id = users[username].get('game_id')
    if not game_id or game_id not in games:
        return
    
    game = games[game_id]
    
    # Nur Ersteller kann Einstellungen ändern
    if game['creator'] != username:
        emit('error', {'message': 'Nur der Ersteller kann Einstellungen ändern'})
        return
    
    # Aktualisiere Einstellungen
    if 'name' in data:
        game['name'] = data['name'].strip()
    if 'is_public' in data:
        game['is_public'] = data['is_public']
    if 'password' in data:
        game['password'] = data['password'].strip()
    if 'settings' in data:
        game['settings'].update(data['settings'])
    
    # Informiere alle Spieler im Raum
    emit('settings_updated', {'game': game}, room=game_id)
    
    # Aktualisiere Lobby
    socketio.emit('lobby_update', {'games': get_public_games()})

@socketio.on('start_game')
def handle_start_game():
    username = None
    for user, user_data in users.items():
        if user_data['sid'] == request.sid:
            username = user
            break
    
    if not username:
        return
    
    game_id = users[username].get('game_id')
    if not game_id or game_id not in games:
        return
    
    game = games[game_id]
    
    # Nur Ersteller kann Spiel starten
    if game['creator'] != username:
        emit('error', {'message': 'Nur der Ersteller kann das Spiel starten'})
        return
    
    if len(game['players']) < 3:
        emit('error', {'message': 'Mindestens 3 Spieler erforderlich'})
        return
    
    game['started'] = True
    
    # Initialisiere Spielzustand
    init_game_state(game)
    
    # Informiere alle Spieler
    emit('game_started', {'game': game}, room=game_id)
    
    # Aktualisiere Lobby
    socketio.emit('lobby_update', {'games': get_public_games()})
    
    # Starte erste Runde
    start_new_round(game_id)

def init_game_state(game):
    """Initialisiert den Spielzustand"""
    # Mische Karten
    question_deck = CARDS_QUESTIONS.copy()
    answer_deck = CARDS_ANSWERS.copy()
    random.shuffle(question_deck)
    random.shuffle(answer_deck)
    
    # Spielerzustand
    player_hands = {}
    player_scores = {}
    
    for player in game['players']:
        player_hands[player] = []
        player_scores[player] = 0
        # Gib jedem Spieler die Anzahl Karten
        for _ in range(game['settings']['max_cards']):
            if answer_deck:
                player_hands[player].append(answer_deck.pop())
    
    game['game_state'] = {
        'question_deck': question_deck,
        'answer_deck': answer_deck,
        'player_hands': player_hands,
        'player_scores': player_scores,
        'current_czar_index': 0,
        'current_question': None,
        'submitted_answers': {},  # {username: [answer_indices]}
        'round_phase': 'waiting',  # waiting, answering, voting, results
        'round_timer': None,
        'round_start_time': None,  # Server-Zeitstempel für Timer-Sync
        'timer_sync_task': None,  # Background task für Timer-Updates
        'paused': False,  # Spiel pausiert
        'pause_time_left': 0  # Verbleibende Zeit beim Pausieren
    }

def start_new_round(game_id):
    """Startet eine neue Runde"""
    if game_id not in games:
        return
    
    game = games[game_id]
    state = game['game_state']
    
    # Wähle Card Czar (rotiert)
    players = game['players']
    czar = players[state['current_czar_index']]
    
    # Ziehe Frage
    if not state['question_deck']:
        # Deck ist leer, mische neu
        state['question_deck'] = CARDS_QUESTIONS.copy()
        random.shuffle(state['question_deck'])
    
    current_question = state['question_deck'].pop()
    state['current_question'] = current_question
    state['submitted_answers'] = {}
    state['round_phase'] = 'answering'
    
    # Sende Rundeninformationen an alle Spieler
    for player in players:
        player_data = {
            'czar': czar,
            'question': current_question,
            'hand': state['player_hands'].get(player, []),
            'scores': state['player_scores'],
            'is_czar': player == czar,
            'answer_time': game['settings'].get('answer_time', 60)
        }
        
        # Finde SID des Spielers
        for username, user_data in users.items():
            if username == player and user_data.get('game_id') == game_id:
                socketio.emit('round_started', player_data, room=user_data['sid'])
                break
    
    # Starte Timer für automatische Abgabe
    answer_time = game['settings'].get('answer_time', 60)
    
    # Stoppe alle laufenden Timer und Tasks
    if state['round_timer']:
        try:
            eventlet.kill(state['round_timer'])
        except:
            pass
        state['round_timer'] = None
    
    if state['timer_sync_task']:
        try:
            state['timer_sync_task'].kill()
        except:
            pass
        state['timer_sync_task'] = None
    
    # Speichere Startzeitpunkt für Timer-Sync
    state['round_start_time'] = time.time()
    state['pause_time_left'] = answer_time  # Speichere Gesamtzeit für Pause-Berechnung
    
    # Verwende eventlet statt threading.Timer
    state['round_timer'] = eventlet.spawn_after(answer_time, auto_submit_answers, game_id)
    
    # Starte Background-Task für regelmäßige Timer-Updates
    if state['timer_sync_task']:
        try:
            state['timer_sync_task'].kill()
        except:
            pass
    
    def sync_timer():
        while game_id in games:
            game = games[game_id]
            state = game['game_state']
            
            if state['round_phase'] != 'answering' or not state['round_start_time'] or state.get('paused', False):
                break
            
            elapsed = time.time() - state['round_start_time']
            time_left = max(0, answer_time - int(elapsed))
            
            socketio.emit('timer_sync', {'time_left': time_left}, room=game_id)
            
            if time_left <= 0:
                break
            
            eventlet.sleep(1)  # Update jede Sekunde
    
    state['timer_sync_task'] = socketio.start_background_task(sync_timer)

def auto_submit_answers(game_id):
    """Automatische Abgabe nach Zeitlimit"""
    if game_id not in games:
        return
    
    game = games[game_id]
    state = game['game_state']
    
    # Prüfe ob pausiert
    if state.get('paused', False):
        return
    
    if state['round_phase'] != 'answering':
        return
    
    # Spieler die noch nicht abgegeben haben
    czar = game['players'][state['current_czar_index']]
    for player in game['players']:
        if player != czar and player not in state['submitted_answers']:
            # Wähle zufällige Karten
            hand = state['player_hands'][player]
            num_blanks = state['current_question']['num_blanks']
            if len(hand) >= num_blanks:
                # Wähle zufällige Indizes
                import random
                indices = random.sample(range(len(hand)), num_blanks)
                state['submitted_answers'][player] = indices
    
    # Gehe zur Voting-Phase
    start_voting_phase(game_id)

@socketio.on('submit_answers')
def handle_submit_answers(data):
    """Spieler gibt Antworten ab"""
    username = None
    for user, user_data in users.items():
        if user_data['sid'] == request.sid:
            username = user
            break
    
    if not username:
        return
    
    game_id = users[username].get('game_id')
    if not game_id or game_id not in games:
        return
    
    game = games[game_id]
    state = game['game_state']
    
    if state.get('paused', False):
        emit('error', {'message': 'Spiel ist pausiert'})
        return
    
    if state['round_phase'] != 'answering':
        emit('error', {'message': 'Nicht in der Antwortphase'})
        return
    
    czar = game['players'][state['current_czar_index']]
    if username == czar:
        emit('error', {'message': 'Der Card Czar darf nicht antworten'})
        return
    
    # Validiere Antworten
    answer_indices = data.get('answer_indices', [])
    num_blanks = state['current_question']['num_blanks']
    
    if len(answer_indices) != num_blanks:
        emit('error', {'message': f'Bitte wähle genau {num_blanks} Karte(n)'})
        return
    
    # Speichere Antworten
    state['submitted_answers'][username] = answer_indices
    
    # Benachrichtige alle über Abgabe
    socketio.emit('player_submitted', {
        'username': username,
        'submitted_count': len(state['submitted_answers']),
        'total_players': len(game['players']) - 1  # -1 für Czar
    }, room=game_id)
    
    # Prüfe ob alle abgegeben haben
    if len(state['submitted_answers']) == len(game['players']) - 1:
        # Stoppe Timer und Sync-Task
        if state['round_timer']:
            try:
                eventlet.kill(state['round_timer'])
            except:
                pass
            state['round_timer'] = None
        if state['timer_sync_task']:
            try:
                state['timer_sync_task'].kill()
            except:
                pass
            state['timer_sync_task'] = None
        start_voting_phase(game_id)

def start_voting_phase(game_id):
    """Startet die Voting-Phase"""
    if game_id not in games:
        return
    
    game = games[game_id]
    state = game['game_state']
    
    state['round_phase'] = 'voting'
    state['round_start_time'] = time.time()  # Timer für Czar
    
    # Czar-Zeit aus Settings
    czar_time = game['settings'].get('czar_time', 30)
    state['pause_time_left'] = czar_time  # Speichere für Pause-Berechnung
    
    # Erstelle anonymisierte Antworten für Voting
    answer_options = []
    player_mapping = []  # Tracking für Gewinner
    
    for player, answer_indices in state['submitted_answers'].items():
        hand = state['player_hands'][player]
        answers = [hand[i] for i in answer_indices]
        answer_options.append(answers)
        player_mapping.append(player)
    
    # Mische Antworten
    combined = list(zip(answer_options, player_mapping))
    random.shuffle(combined)
    answer_options, player_mapping = zip(*combined)
    
    # Speichere Mapping für später
    state['vote_mapping'] = list(player_mapping)
    
    # Sende an alle
    czar = game['players'][state['current_czar_index']]
    
    socketio.emit('voting_phase', {
        'czar': czar,
        'question': state['current_question'],
        'answer_options': [{'answers': opt} for opt in answer_options],
        'czar_time': czar_time
    }, room=game_id)
    
    # Starte Auto-Vote Timer
    def auto_vote_on_timeout():
        if game_id not in games:
            return
        current_game = games[game_id]
        current_state = current_game['game_state']
        
        # Prüfe ob pausiert oder Phase geändert
        if current_state.get('paused', False) or current_state['round_phase'] != 'voting':
            return
        
        # Ändere Phase sofort um doppelte Ausführung zu vermeiden
        current_state['round_phase'] = 'result'
        
        if current_state['vote_mapping']:
            import random
            winner_index = random.randint(0, len(current_state['vote_mapping']) - 1)
            winner = current_state['vote_mapping'][winner_index]
            winner_answer_indices = current_state['submitted_answers'][winner]
            winner_answers = [current_state['player_hands'][winner][i] for i in winner_answer_indices]
            
            current_state['player_scores'][winner] += 1
            
            if current_state['player_scores'][winner] >= current_game['settings']['win_score']:
                end_game(game_id, winner)
            else:
                round_delay = current_game['settings'].get('round_delay', 5)
                socketio.emit('round_result', {
                    'winner': winner,
                    'winner_answers': winner_answers,
                    'question': current_state['current_question'],
                    'scores': current_state['player_scores'],
                    'next_round_in': round_delay
                }, room=game_id)
                
                def next_round():
                    socketio.sleep(float(round_delay))
                    if game_id not in games:
                        return
                    refill_hands(game_id)
                    current_state['current_czar_index'] = (current_state['current_czar_index'] + 1) % len(current_game['players'])
                    start_new_round(game_id)
                
                socketio.start_background_task(next_round)
    
    state['round_timer'] = eventlet.spawn_after(czar_time, auto_vote_on_timeout)
    
    # Starte Timer-Sync für Voting
    if state['timer_sync_task']:
        try:
            state['timer_sync_task'].kill()
        except:
            pass
    
    def sync_czar_timer():
        total_time = czar_time
        while game_id in games:
            current_game = games[game_id]
            current_state = current_game['game_state']
            
            if current_state['round_phase'] != 'voting' or not current_state['round_start_time'] or current_state.get('paused', False):
                break
            
            elapsed = time.time() - current_state['round_start_time']
            time_left = max(0, total_time - int(elapsed))
            
            socketio.emit('timer_sync', {'time_left': time_left}, room=game_id)
            
            if time_left <= 0:
                break
            
            eventlet.sleep(1)
    
    state['timer_sync_task'] = socketio.start_background_task(sync_czar_timer)

@socketio.on('vote_winner')
def handle_vote_winner(data):
    """Card Czar wählt Gewinner"""
    username = None
    for user, user_data in users.items():
        if user_data['sid'] == request.sid:
            username = user
            break
    
    if not username:
        return
    
    game_id = users[username].get('game_id')
    if not game_id or game_id not in games:
        return
    
    game = games[game_id]
    state = game['game_state']
    
    if state.get('paused', False):
        emit('error', {'message': 'Spiel ist pausiert'})
        return
    
    if state['round_phase'] != 'voting':
        emit('error', {'message': 'Nicht in der Voting-Phase'})
        return
    
    czar = game['players'][state['current_czar_index']]
    if username != czar:
        emit('error', {'message': 'Nur der Card Czar darf abstimmen'})
        return
    
    winner_index = data.get('winner_index')
    
    # Finde Gewinner aus dem gespeicherten Mapping
    if 'vote_mapping' not in state or winner_index < 0 or winner_index >= len(state['vote_mapping']):
        emit('error', {'message': 'Ungültiger Index'})
        return
    
    winner = state['vote_mapping'][winner_index]
    
    # Ändere Phase sofort um Race Conditions zu vermeiden
    state['round_phase'] = 'result'
    
    # Stoppe Timer und Timer-Sync
    if state['round_timer']:
        try:
            eventlet.kill(state['round_timer'])
        except:
            pass
        state['round_timer'] = None
    
    if state['timer_sync_task']:
        try:
            state['timer_sync_task'].kill()
        except:
            pass
        state['timer_sync_task'] = None
    
    # Hole die Antworten des Gewinners
    winner_answer_indices = state['submitted_answers'][winner]
    winner_answers = [state['player_hands'][winner][i] for i in winner_answer_indices]
    
    # Punkt vergeben
    state['player_scores'][winner] += 1
    
    # Prüfe auf Spielende
    if state['player_scores'][winner] >= game['settings']['win_score']:
        end_game(game_id, winner)
        return
    
    # Zeige Rundenergebnis
    round_delay = game['settings'].get('round_delay', 5)
    socketio.emit('round_result', {
        'winner': winner,
        'winner_answers': winner_answers,
        'question': state['current_question'],
        'scores': state['player_scores'],
        'next_round_in': round_delay
    }, room=game_id)
    
    # Nach konfigurierbarer Zeit nächste Runde
    def next_round():
        socketio.sleep(float(round_delay))
        if game_id not in games:
            return
        refill_hands(game_id)
        state['current_czar_index'] = (state['current_czar_index'] + 1) % len(game['players'])
        start_new_round(game_id)
    
    socketio.start_background_task(next_round)

def refill_hands(game_id):
    """Füllt Spielerhände wieder auf"""
    if game_id not in games:
        return
    
    game = games[game_id]
    state = game['game_state']
    max_cards = game['settings']['max_cards']
    
    for player in game['players']:
        hand = state['player_hands'][player]
        # Entferne gespielte Karten
        if player in state['submitted_answers']:
            indices = sorted(state['submitted_answers'][player], reverse=True)
            for idx in indices:
                if idx < len(hand):
                    hand.pop(idx)
        
        # Fülle auf
        while len(hand) < max_cards and state['answer_deck']:
            hand.append(state['answer_deck'].pop())

def end_game(game_id, winner):
    """Beendet das Spiel"""
    if game_id not in games:
        return
    
    game = games[game_id]
    state = game['game_state']
    
    socketio.emit('game_ended', {
        'winner': winner,
        'final_scores': state['player_scores']
    }, room=game_id)
    
    # Reset Spiel
    game['started'] = False
    game['game_state'] = None
    socketio.emit('lobby_update', {'games': get_public_games()})

@socketio.on('pause_game')
def handle_pause_game():
    username = None
    for user, user_data in users.items():
        if user_data['sid'] == request.sid:
            username = user
            break
    
    if not username:
        return
    
    game_id = users[username].get('game_id')
    if not game_id or game_id not in games:
        return
    
    game = games[game_id]
    
    # Nur Ersteller kann pausieren
    if game['creator'] != username:
        emit('error', {'message': 'Nur der Ersteller kann das Spiel pausieren'})
        return
    
    if not game['started']:
        return
    
    state = game['game_state']
    
    if state['paused']:
        return
    
    state['paused'] = True
    
    # Berechne verbleibende Zeit basierend auf der seit Resume verstrichenen Zeit
    if state['round_start_time'] and 'pause_time_left' in state:
        elapsed_since_resume = time.time() - state['round_start_time']
        # Ziehe die seit Resume verstrichene Zeit von der verbleibenden Zeit ab
        state['pause_time_left'] = max(1, state['pause_time_left'] - int(elapsed_since_resume))
    
    # Stoppe Timer
    if state['round_timer']:
        try:
            eventlet.kill(state['round_timer'])
        except:
            pass
        state['round_timer'] = None
    
    if state['timer_sync_task']:
        try:
            state['timer_sync_task'].kill()
        except:
            pass
        state['timer_sync_task'] = None
    
    # Informiere alle Spieler mit verbleibender Zeit
    socketio.emit('game_paused', {'time_left': state.get('pause_time_left', 0)}, room=game_id)

@socketio.on('resume_game')
def handle_resume_game():
    username = None
    for user, user_data in users.items():
        if user_data['sid'] == request.sid:
            username = user
            break
    
    if not username:
        return
    
    game_id = users[username].get('game_id')
    if not game_id or game_id not in games:
        return
    
    game = games[game_id]
    
    # Nur Ersteller kann fortsetzen
    if game['creator'] != username:
        emit('error', {'message': 'Nur der Ersteller kann das Spiel fortsetzen'})
        return
    
    if not game['started']:
        return
    
    state = game['game_state']
    
    if not state['paused']:
        return
    
    state['paused'] = False
    
    # Starte Timer neu mit verbleibender Zeit
    if state['pause_time_left'] > 0:
        state['round_start_time'] = time.time()
        
        if state['round_phase'] == 'answering':
            remaining_time = state['pause_time_left']
            state['round_timer'] = eventlet.spawn_after(remaining_time, auto_submit_answers, game_id)
            
            def sync_timer():
                answer_time = remaining_time
                start_offset = time.time()
                while game_id in games:
                    current_game = games[game_id]
                    current_state = current_game['game_state']
                    
                    if current_state['round_phase'] != 'answering' or not current_state['round_start_time'] or current_state.get('paused', False):
                        break
                    
                    elapsed = time.time() - start_offset
                    time_left = max(0, answer_time - int(elapsed))
                    
                    socketio.emit('timer_sync', {'time_left': time_left}, room=game_id)
                    
                    if time_left <= 0:
                        break
                    
                    eventlet.sleep(1)
            
            state['timer_sync_task'] = socketio.start_background_task(sync_timer)
            
        elif state['round_phase'] == 'voting':
            # Voting-Phase Timer
            czar_time = state['pause_time_left']
            
            # Starte Auto-Vote Timer
            def auto_vote_after_pause():
                if game_id not in games:
                    return
                current_game = games[game_id]
                current_state = current_game['game_state']
                
                # Prüfe ob pausiert oder Phase geändert
                if current_state.get('paused', False) or current_state['round_phase'] != 'voting':
                    return
                
                if current_state['vote_mapping']:
                    winner_index = random.randint(0, len(current_state['vote_mapping']) - 1)
                    winner = current_state['vote_mapping'][winner_index]
                    winner_answer_indices = current_state['submitted_answers'][winner]
                    winner_answers = [current_state['player_hands'][winner][i] for i in winner_answer_indices]
                    
                    # Stoppe Timer
                    if current_state['round_timer']:
                        try:
                            eventlet.kill(current_state['round_timer'])
                        except:
                            pass
                        current_state['round_timer'] = None
                    
                    current_state['player_scores'][winner] += 1
                    
                    if current_state['player_scores'][winner] >= current_game['settings']['win_score']:
                        end_game(game_id, winner)
                    else:
                        round_delay = current_game['settings'].get('round_delay', 5)
                        socketio.emit('round_result', {
                            'winner': winner,
                            'winner_answers': winner_answers,
                            'question': current_state['current_question'],
                            'scores': current_state['player_scores'],
                            'next_round_in': round_delay
                        }, room=game_id)
                        
                        def next_round():
                            socketio.sleep(float(round_delay))
                            if game_id not in games:
                                return
                            refill_hands(game_id)
                            current_state['current_czar_index'] = (current_state['current_czar_index'] + 1) % len(current_game['players'])
                            start_new_round(game_id)
                        
                        socketio.start_background_task(next_round)
            
            state['round_timer'] = eventlet.spawn_after(czar_time, auto_vote_after_pause)
            
            def sync_czar_timer():
                remaining_czar_time = czar_time
                start_offset = time.time()
                while game_id in games:
                    current_game = games[game_id]
                    current_state = current_game['game_state']
                    
                    if current_state['round_phase'] != 'voting' or not current_state['round_start_time'] or current_state.get('paused', False):
                        break
                    
                    elapsed = time.time() - start_offset
                    time_left = max(0, remaining_czar_time - int(elapsed))
                    
                    socketio.emit('timer_sync', {'time_left': time_left}, room=game_id)
                    
                    if time_left <= 0:
                        break
                    
                    eventlet.sleep(1)
            
            state['timer_sync_task'] = socketio.start_background_task(sync_czar_timer)
    
    # Informiere alle Spieler
    socketio.emit('game_resumed', {
        'time_left': state['pause_time_left']
    }, room=game_id)

@socketio.on('reset_to_lobby')
def handle_reset_to_lobby():
    username = None
    for user, user_data in users.items():
        if user_data['sid'] == request.sid:
            username = user
            break
    
    if not username:
        return
    
    game_id = users[username].get('game_id')
    if not game_id or game_id not in games:
        return
    
    game = games[game_id]
    
    # Nur Ersteller kann zurück zur Lobby
    if game['creator'] != username:
        emit('error', {'message': 'Nur der Ersteller kann das Spiel zurücksetzen'})
        return
    
    # Reset Spiel
    game['started'] = False
    game['game_state'] = None
    
    # Informiere alle Spieler
    socketio.emit('game_reset_to_lobby', {'game': game}, room=game_id)
    socketio.emit('lobby_update', {'games': get_public_games()})

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
