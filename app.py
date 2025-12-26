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
disconnect_timers = {}  # {username: timestamp of disconnect}
global_timer_task = None  # Globaler Timer-Task
timer_started = False  # Flag ob Timer bereits gestartet wurde

# Globaler Timer-Task
def universal_timer_task():
    """Universeller Timer der alle Spiele durchläuft und Timer aktualisiert"""
    print("Universal Timer Task gestartet", flush=True)
    while True:
        try:
            # Durchlaufe alle disconnected Benutzer und bereinige nach 30 Sekunden
            current_time = time.time()
            for username in list(disconnect_timers.keys()):
                disconnect_time = disconnect_timers[username]
                if current_time - disconnect_time >= 30:
                    print(f"Bereinige Benutzer nach 30 Sekunden Inaktivität: {username}", flush=True)
                    cleanup_user(username)

            # Durchlaufe alle aktiven Spiele
            for game_id in list(games.keys()):
                if game_id not in games:
                    continue
                    
                game = games[game_id]
                
                # Nur laufende Spiele
                if not game.get('started') or not game.get('game_state'):
                    continue
                
                state = game['game_state']
                
                # Pausierte Spiele überspringen
                if state.get('paused', False):
                    continue
                
                # Timer runterzählen wenn aktiv
                if state.get('timer', -1) > 0:
                    state['timer'] -= 1
                    
                    # Sende Timer-Update an Clients
                    socketio.emit('timer_sync', {'time_left': state['timer']}, room=game_id)
                    
                    # Timer abgelaufen (0 erreicht)
                    if state['timer'] == 0:
                        handle_timer_expired(game_id)
                        
            eventlet.sleep(1)
        except Exception as e:
            print(f"Error in universal_timer_task: {e}", flush=True)
            eventlet.sleep(1)

def handle_timer_expired(game_id):
    """Behandelt abgelaufene Timer basierend auf Phase"""
    if game_id not in games:
        return
        
    game = games[game_id]
    state = game['game_state']
    phase = state.get('round_phase')
    
    if phase == 'answering':
        # Auto-Submit für alle Spieler die noch nicht abgegeben haben
        auto_submit_all_players(game_id)
    elif phase == 'voting':
        # Auto-Vote für Czar
        auto_vote_random_winner(game_id)

def broadcastPublicGames():
    socketio.emit('public_games_list', {'games': get_public_games()})

def auto_submit_all_players(game_id):
    """Automatisches Abgeben für alle Spieler die noch nicht abgegeben haben"""
    if game_id not in games:
        return
    
    game = games[game_id]
    state = game['game_state']
    czar = None
    if state.get('active_players') and isinstance(state.get('current_czar_index'), int):
        if 0 <= state['current_czar_index'] < len(state['active_players']):
            czar = state['active_players'][state['current_czar_index']]
    
    for player in state['active_players']:
        if player == czar:
            continue
        if player in state['submitted_answers']:
            continue
            
        # Wähle automatisch Karten aus
        hand = state['player_hands'][player]
        num_needed = state['current_question']['num_blanks']
        available_indices = list(range(len(hand)))
        
        if len(available_indices) >= num_needed:
            selected = random.sample(available_indices, num_needed)
            state['submitted_answers'][player] = sorted(selected)
    
    # Starte Voting-Phase
    start_voting_phase(game_id)

def auto_vote_random_winner(game_id):
    """Wählt automatisch einen zufälligen Gewinner aus"""
    if game_id not in games:
        return
        
    game = games[game_id]
    state = game['game_state']
    
    if not state.get('vote_mapping'):
        return
    
    winner_index = random.randint(0, len(state['vote_mapping']) - 1)
    process_winner_selection(game_id, winner_index)

def process_winner_selection(game_id, winner_index):
    """Verarbeitet die Gewinner-Auswahl (manuell oder automatisch)"""
    if game_id not in games:
        return
        
    game = games[game_id]
    state = game['game_state']
    
    # Prüfe ob Phase noch voting ist
    if state['round_phase'] != 'voting':
        return
    
    # Ändere Phase sofort
    state['round_phase'] = 'result'
    state['timer'] = -1  # Timer ausblenden
    
    winner = state['vote_mapping'][winner_index]
    
    # Prüfe ob Gewinner noch im Spiel ist
    if winner not in state['player_scores']:
        # Gewinner wurde disconnected und entfernt - kein Punkt vergeben
        print(f"Winner {winner} was disconnected, no points awarded", flush=True)
        
        # Versuche trotzdem die Antworten zu zeigen (falls noch in submitted_answers)
        winner_answers = []
        if winner in state['submitted_answers']:
            # Antworten könnten noch da sein
            try:
                winner_answer_indices = state['submitted_answers'][winner]
                # Hand könnte aber gelöscht sein
                if winner in state['player_hands']:
                    winner_answers = [state['player_hands'][winner][i] for i in winner_answer_indices]
            except (KeyError, IndexError):
                pass
        
        # Zeige Rundenergebnis ohne Punktvergabe
        round_delay = game['settings'].get('round_delay', 5)
        socketio.emit('round_result', {
            'winner': None,
            'disconnected_player': winner,
            'winner_answers': winner_answers,
            'question': state['current_question'],
            'scores': state['player_scores'],
            'next_round_in': round_delay
        }, room=game_id)
        
        # Nächste Runde nach Verzögerung
        def next_round():
            socketio.sleep(float(round_delay))
            if game_id not in games:
                return
            refill_hands(game_id)
            state['current_czar_index'] = (state['current_czar_index'] + 1) % len(game['players'])
            start_new_round(game_id)
        
        socketio.start_background_task(next_round)
        return
    
    winner_answer_indices = state['submitted_answers'][winner]
    winner_answers = [state['player_hands'][winner][i] for i in winner_answer_indices]
    
    # Punkt vergeben
    state['player_scores'][winner] += 1
    
    # Speichere Runde in History
    czar = None
    if state.get('active_players') and isinstance(state.get('current_czar_index'), int):
        if 0 <= state['current_czar_index'] < len(state['active_players']):
            czar = state['active_players'][state['current_czar_index']]
    round_number = len(state['round_history']) + 1
    state['round_history'].append({
        'round_num': round_number,
        'question': state['current_question'],
        'czar': czar,
        'winner': winner,
        'winner_answers': winner_answers
    })
    
    # Zeige Rundenergebnis
    round_delay = game['settings'].get('round_delay', 5)
    socketio.emit('round_result', {
        'winner': winner,
        'winner_answers': winner_answers,
        'winner_index': winner_index,
        'question': state['current_question'],
        'scores': state['player_scores'],
        'next_round_in': round_delay
    }, room=game_id)
    
    # Prüfe auf Spielende (Punkte-Limit oder Runden-Limit erreicht)
    max_rounds = game['settings'].get('max_rounds', 50)
    rounds_played = len(state['round_history'])
    
    if state['player_scores'][winner] >= game['settings']['win_score'] or rounds_played >= max_rounds:
        # Spiel ist vorbei - zeige erst Rundenergebnis, dann nach Delay Spielende
        def show_game_end():
            socketio.sleep(float(round_delay))
            if game_id in games:
                end_game(game_id, winner)
        
        socketio.start_background_task(show_game_end)
        return
    
    # Nächste Runde nach Verzögerung
    def next_round():
        socketio.sleep(float(round_delay))
        if game_id not in games:
            return
        refill_hands(game_id)
        state['current_czar_index'] = (state['current_czar_index'] + 1) % len(game['players'])
        start_new_round(game_id)
    
    socketio.start_background_task(next_round)

def ensure_valid_creator(game_id):
    """Stellt sicher, dass der Creator des Spiels noch existiert, ansonsten wird ein neuer gewählt"""
    if game_id not in games:
        return
    
    game = games[game_id]
    creator = game.get('creator')
    
    # Prüfe ob Creator noch existiert und im Spiel ist
    creator_exists = (
        creator and 
        creator in users and 
        (creator in game['players'] or creator in game.get('spectators', []))
    )
    
    if not creator_exists:
        # Wähle neuen Creator
        if game['players']:
            game['creator'] = game['players'][0]
        elif game.get('spectators'):
            game['creator'] = game['spectators'][0]
        else:
            game['creator'] = None
        
        # Informiere alle im Raum über den neuen Creator
        if game['creator']:
            socketio.emit('creator_changed', {
                'creator': game['creator']
            }, room=game_id)

def cleanup_user(username):
    """Entfernt Benutzer nach 30 Sekunden Inaktivität"""
    if username in users:
        game_id = users[username].get('game_id')
        if game_id and game_id in games:
            game = games[game_id]
            
            # Entferne Spieler aus dem Spiel
            was_creator = game['creator'] == username
            if username in game['players']:
                game['players'].remove(username)
            if username in game.get('spectators', []):
                game['spectators'].remove(username)
                
            # Entferne aus Game State (Scores, Hands, etc.)
            if game.get('game_state'):
                state = game['game_state']
                if username in state.get('player_scores', {}):
                    del state['player_scores'][username]
                if username in state.get('player_hands', {}):
                    del state['player_hands'][username]
                if username in state.get('submitted_answers', {}):
                    del state['submitted_answers'][username]
                if username in state.get('active_players', []):
                    state['active_players'].remove(username)
            
            # Wenn Ersteller weg ist, neuen Ersteller bestimmen
            if was_creator:
                if game['players']:
                    game['creator'] = game['players'][0]
                elif game.get('spectators'):
                    game['creator'] = game['spectators'][0]
                else:
                    game['creator'] = None
            
            # Spiel löschen wenn leer
            if not game['players'] and not game.get('spectators'):
                # Timer wird automatisch vom universal_timer_task gestoppt
                # wenn das Spiel nicht mehr existiert
                del games[game_id]
            else:
                # Informiere andere Spieler
                socketio.emit('player_left', {
                    'username': username,
                    'players': game['players'],
                    'spectators': game.get('spectators', []),
                    'creator': game['creator']
                }, room=game_id)
        
        del users[username]
        if username in disconnect_timers:
            del disconnect_timers[username]

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    global global_timer_task, timer_started
    print(f'Client connected: {request.sid}', flush=True)
    
    # Starte Timer beim ersten Connect
    if not timer_started:
        timer_started = True
        print("Starte Universal Timer Task...", flush=True)
        global_timer_task = socketio.start_background_task(universal_timer_task)
        print("Universal Timer Task wurde gestartet", flush=True)

@socketio.on('disconnect')
def handle_disconnect():
    print(f'Client disconnected: {request.sid}', flush=True)
    # Finde Benutzer mit dieser SID
    username = None
    for user, data in users.items():
        if data['sid'] == request.sid:
            username = user
            break
    
    if username:
        # Markiere als disconnecting
        users[username]['status'] = 'disconnecting'
        
        # Informiere Mitspieler über Status-Änderung
        game_id = users[username].get('game_id')
        if game_id and game_id in games:
            socketio.emit('player_status_changed', {
                'username': username,
                'status': 'disconnecting'
            }, room=game_id)
        
        disconnect_timers[username] = time.time()

@socketio.on('set_username')
def handle_set_username(data):
    username = data.get('username', '').strip()
    
    if not username:
        emit('username_error', {'message': 'Bitte gib einen Namen ein'})
        return
    
    # Bereinige Username: Ersetze mehrfache Leerzeichen durch ein einzelnes
    import re
    username = re.sub(r'\s+', ' ', username).strip()
    
    # Prüfe Länge
    if len(username) < 2:
        emit('username_error', {'message': 'Der Name muss mindestens 2 Zeichen lang sein'})
        return
    
    if len(username) > 20:
        emit('username_error', {'message': 'Der Name darf maximal 20 Zeichen lang sein'})
        return
    
    # Prüfe ob Name bereits existiert und Spieler verbunden ist
    if username in users:
        # Wenn es der gleiche Benutzer ist (Reconnect)
        if users[username]['sid'] == request.sid:
            emit('username_set', {'username': username})
            return
        
        # Prüfe ob der andere Spieler noch verbunden ist
        user_status = users[username].get('status', 'connected')
        if user_status == 'connected':
            emit('username_error', {'message': 'Dieser Name ist bereits vergeben'})
            return
        
        # Wenn der andere Spieler disconnecting ist, erlaube den Namen nicht
        # (30 Sekunden Grace Period)
        emit('username_error', {'message': 'Dieser Name wird gerade verwendet. Bitte warte kurz oder wähle einen anderen Namen.'})
        return
    
    # Registriere Benutzer
    users[username] = {
        'sid': request.sid,
        'last_seen': time.time(),
        'game_id': None,
        'status': 'connected'
    }
    
    # Lösche eventuellen Timer
    if username in disconnect_timers:
        del disconnect_timers[username]
    
    emit('username_set', {'username': username})
    print(f'Username set: {username}', flush=True)

@socketio.on('reconnect_user')
def handle_reconnect(data):
    username = data.get('username', '').strip()
    
    if username in users:
        # Aktualisiere SID
        users[username]['sid'] = request.sid
        users[username]['last_seen'] = time.time()
        users[username]['status'] = 'connected'
        
        # Lösche Timer
        if username in disconnect_timers:
            del disconnect_timers[username]
        
        game_id = users[username].get('game_id')
        if game_id and game_id in games:
            # Informiere über Reconnect
            socketio.emit('player_status_changed', {
                'username': username,
                'status': 'connected'
            }, room=game_id)
        if game_id and game_id in games:
            # Trete Raum wieder bei
            join_room(game_id)
            
            game = games[game_id]
            reconnect_data = {
                'username': username,
                'game_id': game_id,
                'game': game,
                'is_spectator': users[username].get('is_spectator', False)
            }
            
            # Player Status hinzufügen
            player_statuses = {}
            for player in game['players']:
                if player in users:
                    player_statuses[player] = users[player].get('status', 'connected')
                else:
                    player_statuses[player] = 'disconnected'
            reconnect_data['player_statuses'] = player_statuses
            
            # Spectator Status hinzufügen
            spectator_statuses = {}
            for spectator in game.get('spectators', []):
                if spectator in users:
                    spectator_statuses[spectator] = users[spectator].get('status', 'connected')
                else:
                    spectator_statuses[spectator] = 'disconnected'
            reconnect_data['spectator_statuses'] = spectator_statuses
            
            # Wenn Spiel läuft, sende aktuellen Spielzustand
            if game['started'] and game.get('game_state'):
                state = game['game_state']
                players = game['players']
                czar = None
                if players and isinstance(state.get('current_czar_index'), int):
                    if 0 <= state['current_czar_index'] < len(players):
                        czar = players[state['current_czar_index']]
                # Grundlegende Spielinformationen
                reconnect_data['game_started'] = True
                reconnect_data['round_phase'] = state.get('round_phase')
                reconnect_data['czar'] = czar
                reconnect_data['is_czar'] = username == czar if czar is not None else False
                reconnect_data['scores'] = state['player_scores']
                reconnect_data['timer'] = state.get('timer', -1)
                reconnect_data['paused'] = state.get('paused', False)
                
                # Phase-spezifische Daten (nur für Spieler, nicht für Spectators)
                is_spectator = users[username].get('is_spectator', False)
                
                if state.get('round_phase') in ['answering', 'voting', 'result']:
                    reconnect_data['question'] = state['current_question']
                    if not is_spectator:
                        reconnect_data['hand'] = state['player_hands'].get(username, [])
                    else:
                        reconnect_data['hand'] = []  # Spectators haben keine Karten
                
                if state.get('round_phase') == 'answering':
                    if not is_spectator:
                        reconnect_data['has_submitted'] = username in state['submitted_answers']
                    reconnect_data['submitted_count'] = len(state['submitted_answers'])
                    reconnect_data['total_players'] = len(players) - 1
                
                if state.get('round_phase') == 'voting':
                    # Erstelle anonymisierte Antworten
                    answer_options = []
                    for player in state.get('vote_mapping', []):
                        answer_indices = state['submitted_answers'].get(player, [])
                        hand = state['player_hands'].get(player, [])
                        answers = [hand[i] for i in answer_indices if i < len(hand)]
                        answer_options.append({'answers': answers})
                    reconnect_data['answer_options'] = answer_options
            
            # Stelle sicher, dass der Creator noch existiert
            ensure_valid_creator(game_id)
            
            emit('reconnected', reconnect_data)
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
        'spectators': [],  # Zuschauer die nicht aktiv mitspielen
        'is_public': is_public,
        'password': password,
        'settings': {
            'max_cards': 7,
            'win_score': 10,
            'max_rounds': 50,  # Maximum Anzahl Runden
            'answer_time': 60,  # Sekunden für automatische Abgabe
            'round_delay': 5,  # Sekunden zwischen Runden
            'czar_time': 30  # Sekunden für Card Czar Voting
        },
        'started': False,
        'game_state': None  # Wird gesetzt wenn Spiel startet
    }
    
    users[username]['game_id'] = game_id
    join_room(game_id)
    
    emit('game_created', games[game_id])
    # Aktualisiere Lobby für alle
    broadcastPublicGames()

@socketio.on('get_public_games')
def handle_get_public_games():
    emit('public_games_list', {'games': get_public_games()})

@socketio.on('get_game_info_link_join')
def handle_get_game_info(data):
    game_id = data.get('game_id')
    if game_id not in games:
        emit('game_info_link_join_error', {'message': 'Spiel nicht gefunden'})
        return
    
    game = games[game_id]
    emit('game_info_link_join', {
        'id': game_id,
        'name': game['name'],
        'has_password': bool(game['password']),
        'started': game['started']
    })

def get_public_games():
    """Gibt alle öffentlichen Spiele zurück"""
    public_games = []
    for game_id, game in games.items():
        if game['is_public']: #and not game['started']:
            public_games.append({
                'id': game_id,
                'name': game['name'],
                'players': len(game['players']),
                'has_password': bool(game['password'])
            })
    return public_games

@socketio.on('get_game_state')
def handle_get_game_state():
    """Sendet den aktuellen Spielzustand an den anfragenden Client"""
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
    
    # Sammle Player-Status-Infos
    player_statuses = {}
    for player in game['players']:
        if player in users:
            player_statuses[player] = users[player].get('status', 'connected')
        else:
            player_statuses[player] = 'disconnected'
    
    spectator_statuses = {}
    for spectator in game.get('spectators', []):
        if spectator in users:
            spectator_statuses[spectator] = users[spectator].get('status', 'connected')
        else:
            spectator_statuses[spectator] = 'disconnected'
    
    emit('game_state_update', {
        'game': game,
        'player_statuses': player_statuses,
        'spectator_statuses': spectator_statuses
    })

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
    is_spectator = data.get('is_spectator', False)  # Ob als Zuschauer beigetreten wird
    
    if game_id not in games:
        emit('error', {'message': 'Spiel nicht gefunden'})
        return
    
    game = games[game_id]
    
    # Prüfe Passwort
    if game['password'] and game['password'] != password:
        emit('error', {'message': 'Falsches Passwort'})
        return
    
    # Füge Spieler oder Spectator hinzu
    if is_spectator:
        # Als Zuschauer beitreten
        if username not in game['spectators'] and username not in game['players']:
            game['spectators'].append(username)
        users[username]['is_spectator'] = True
    else:
        # Als aktiver Spieler beitreten
        if username not in game['players'] and username not in game['spectators']:
            game['players'].append(username)
            
            # Wenn Spiel läuft, initialisiere Spieler-Zustand für nächste Runde
            if game['started'] and game.get('game_state'):
                state = game['game_state']
                # Füge leere Hand und Score hinzu
                state['player_hands'][username] = []
                state['player_scores'][username] = 0
                # Spieler wird in der nächsten Runde Karten bekommen (via refill_hands)
        users[username]['is_spectator'] = False
    
    users[username]['game_id'] = game_id
    join_room(game_id)
    
    # Sammle Player-Status-Infos
    player_statuses = {}
    for player in game['players']:
        if player in users:
            player_statuses[player] = users[player].get('status', 'connected')
        else:
            player_statuses[player] = 'disconnected'
    
    spectator_statuses = {}
    for spectator in game['spectators']:
        if spectator in users:
            spectator_statuses[spectator] = users[spectator].get('status', 'connected')
        else:
            spectator_statuses[spectator] = 'disconnected'
    
    # Basis-Daten für Join
    join_data = {
        'game_id': game_id, 
        'game': game, 
        'player_statuses': player_statuses,
        'spectator_statuses': spectator_statuses,
        'is_spectator': is_spectator
    }
    
    # Wenn Spiel läuft, sende zusätzliche Runden-Informationen
    if game['started'] and game.get('game_state'):
        state = game['game_state']
        join_data['game_started'] = True
        join_data['round_phase'] = state.get('round_phase')
        join_data['scores'] = state.get('player_scores', {})
        join_data['paused'] = state.get('paused', False)
        
        # Aktive Spieler für Czar
        players = [p for p in game['players'] if p in state.get('active_players', [])]
        
        if players and state.get('current_czar_index') is not None:
            czar_index = state['current_czar_index']
            if czar_index < len(players):
                join_data['czar'] = players[czar_index]
                join_data['is_czar'] = (username == players[czar_index])
        
        # Round info
        join_data['current_round'] = len(state.get('round_history', [])) + 1
        join_data['max_rounds'] = game['settings'].get('max_rounds', 50)
        join_data['win_score'] = game['settings']['win_score']
        join_data['answer_time'] = game['settings']['answer_time']
        join_data['czar_time'] = game['settings']['czar_time']
        
        # Timer
        if state.get('timer_running'):
            elapsed = time.time() - state.get('phase_start_time', time.time())
            max_time = game['settings']['answer_time'] if state.get('round_phase') == 'answering' else game['settings']['czar_time']
            join_data['timer'] = max(0, int(max_time - elapsed))
        
        # Phase-spezifische Daten
        if state.get('round_phase') in ['answering', 'voting', 'result']:
            join_data['question'] = state['current_question']
            
            # Spectators bekommen keine Hand
            if not is_spectator and username in state.get('player_hands', {}):
                join_data['hand'] = state['player_hands'].get(username, [])
            else:
                join_data['hand'] = []
        
        if state.get('round_phase') == 'answering':
            if not is_spectator and username in state.get('submitted_answers', {}):
                join_data['has_submitted'] = True
            join_data['submitted_count'] = len(state.get('submitted_answers', {}))
            join_data['total_players'] = len(players) - 1 if players else 0
        
        if state.get('round_phase') == 'voting':
            # Erstelle anonymisierte Antworten
            answer_options = []
            for player in state.get('vote_mapping', []):
                answer_indices = state['submitted_answers'].get(player, [])
                hand = state['player_hands'].get(player, [])
                answers = [hand[i] for i in answer_indices if i < len(hand)]
                answer_options.append({'answers': answers})
            join_data['answer_options'] = answer_options
    
    emit('game_joined', join_data)
    
    # Informiere andere Spieler
    emit('player_joined', {
        'username': username,
        'is_spectator': is_spectator,
        'players': game['players'],
        'spectators': game['spectators'],
        'creator': game['creator']
    }, room=game_id, include_self=False)
    
    # Aktualisiere Lobby
    broadcastPublicGames()

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
    
    # Entferne Spieler aus players oder spectators
    was_creator = game['creator'] == username
    if username in game['players']:
        game['players'].remove(username)
    if username in game.get('spectators', []):
        game['spectators'].remove(username)
    
    # Wenn Ersteller weg ist, neuen Ersteller bestimmen
    if was_creator:
        # Wähle nächsten Spieler, falls vorhanden
        if game['players']:
            game['creator'] = game['players'][0]
        # Ansonsten nächsten Spectator
        elif game.get('spectators'):
            game['creator'] = game['spectators'][0]
        else:
            # Keine Spieler mehr übrig
            game['creator'] = None
    
    users[username]['game_id'] = None
    leave_room(game_id)
    
    # Spiel löschen wenn leer
    if not game['players'] and not game.get('spectators'):
        # Timer wird automatisch vom universal_timer_task gestoppt
        del games[game_id]
    else:
        # Informiere andere Spieler
        emit('player_left', {
            'username': username,
            'players': game['players'],
            'spectators': game.get('spectators', []),
            'creator': game['creator']
        }, room=game_id)
    
    emit('left_game', {})
    # Aktualisiere Lobby
    broadcastPublicGames()



@socketio.on('kick_player')
def handle_kick_player(data):
    kicker = None
    for user, user_data in users.items():
        if user_data['sid'] == request.sid:
            kicker = user
            break
    
    if not kicker:
        return
    
    game_id = users[kicker].get('game_id')
    if not game_id or game_id not in games:
        return
    
    game = games[game_id]
    
    # Nur Creator kann kicken
    if game['creator'] != kicker:
        emit('error', {'message': 'Nur der Ersteller kann Spieler kicken'})
        return
    
    # Spiel darf nicht gestartet sein
    if game['started']:
        emit('error', {'message': 'Spieler können während des Spiels nicht gekickt werden'})
        return
    
    kicked_user = data.get('username')
    
    # Prüfe ob in players oder spectators
    if kicked_user in game['players']:
        game['players'].remove(kicked_user)
    elif kicked_user in game.get('spectators', []):
        game['spectators'].remove(kicked_user)
    else:
        return
    
    # Creator kann sich nicht selbst kicken
    if kicked_user == kicker:
        emit('error', {'message': 'Du kannst dich nicht selbst kicken'})
        return
    
    # Update user state
    if kicked_user in users:
        users[kicked_user]['game_id'] = None
        # Informiere gekickten Spieler
        kicked_sid = users[kicked_user]['sid']
        socketio.emit('kicked_from_game', {
            'message': f'Du wurdest von {kicker} aus dem Spiel entfernt'
        }, room=kicked_sid)
    
    # Informiere alle anderen
    socketio.emit('player_left', {
        'username': kicked_user,
        'players': game['players'],
        'spectators': game.get('spectators', []),
        'creator': game['creator']
    }, room=game_id)
    
    broadcastPublicGames()

@socketio.on('toggle_role')
def handle_toggle_role():
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
    
    # Spiel darf nicht gestartet sein
    if game['started']:
        emit('error', {'message': 'Rolle kann während des Spiels nicht gewechselt werden'})
        return
    
    is_spectator = users[username].get('is_spectator', False)
    
    if is_spectator:
        # Von Spectator zu Player wechseln
        if username in game.get('spectators', []):
            game['spectators'].remove(username)
        if username not in game['players']:
            game['players'].append(username)
        users[username]['is_spectator'] = False
        new_role = 'Spieler'
    else:
        # Von Player zu Spectator wechseln
        if username in game['players']:
            game['players'].remove(username)
        if username not in game.get('spectators', []):
            game['spectators'].append(username)
        users[username]['is_spectator'] = True
        new_role = 'Zuschauer'
    
    # Informiere alle im Raum
    emit('role_changed', {
        'username': username,
        'is_spectator': users[username]['is_spectator'],
        'players': game['players'],
        'spectators': game.get('spectators', [])
    }, room=game_id)
    
    emit('success', {'message': f'Du bist jetzt {new_role}'})

@socketio.on('force_role')
def handle_force_role(data):
    """Creator erzwingt Rollenwechsel für anderen Spieler"""
    creator = None
    for user, user_data in users.items():
        if user_data['sid'] == request.sid:
            creator = user
            break
    
    if not creator:
        return
    
    game_id = users[creator].get('game_id')
    if not game_id or game_id not in games:
        return
    
    game = games[game_id]
    
    # Nur Creator kann Rollen erzwingen
    if game['creator'] != creator:
        emit('error', {'message': 'Nur der Ersteller kann Rollen ändern'})
        return
    
    # Spiel darf nicht gestartet sein
    if game['started']:
        emit('error', {'message': 'Rolle kann während des Spiels nicht gewechselt werden'})
        return
    
    target_username = data.get('username')
    if not target_username or target_username not in users:
        return
    
    # Creator kann sich selbst nicht verschieben (dafür toggle_role nutzen)
    if target_username == creator:
        emit('error', {'message': 'Nutze deinen eigenen Toggle-Button um deine Rolle zu ändern'})
        return
    
    is_spectator = users[target_username].get('is_spectator', False)
    
    if is_spectator:
        # Von Spectator zu Player verschieben
        if target_username in game.get('spectators', []):
            game['spectators'].remove(target_username)
        if target_username not in game['players']:
            game['players'].append(target_username)
        users[target_username]['is_spectator'] = False
        new_role = 'Spieler'
    else:
        # Von Player zu Spectator verschieben
        if target_username in game['players']:
            game['players'].remove(target_username)
        if target_username not in game.get('spectators', []):
            game['spectators'].append(target_username)
        users[target_username]['is_spectator'] = True
        new_role = 'Zuschauer'
    
    # Informiere alle im Raum
    emit('role_changed', {
        'username': target_username,
        'is_spectator': users[target_username]['is_spectator'],
        'players': game['players'],
        'spectators': game.get('spectators', []),
        'forced_by': creator
    }, room=game_id)

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
    broadcastPublicGames()

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
    
    # Stelle sicher, dass der Creator noch existiert
    ensure_valid_creator(game_id)
    
    # Nur Ersteller kann Spiel starten
    if game['creator'] != username:
        emit('error', {'message': 'Nur der Ersteller kann das Spiel starten'})
        return
    
    # Zähle nur aktive Spieler (keine Spectators)
    active_player_count = len(game['players'])
    if active_player_count < 3:
        emit('error', {'message': 'Mindestens 3 aktive Spieler erforderlich (Zuschauer zählen nicht)'})
        return
    
    game['started'] = True
    
    # Initialisiere Spielzustand
    init_game_state(game)
    
    # Informiere alle Spieler
    emit('game_started', {'game': game}, room=game_id)
    
    # Aktualisiere Lobby
    broadcastPublicGames()
    
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
        'round_phase': 'waiting',  # waiting, answering, voting, result
        'timer': -1,  # Aktueller Timer-Wert, -1 = ausgeblendet
        'paused': False,  # Spiel pausiert
        'active_players': [],  # Spieler die in der aktuellen Runde aktiv sind
        'round_history': []  # History aller Runden: [{round_num, question, czar, winner, winner_answers}]
    }

def start_new_round(game_id):
    """Startet eine neue Runde"""
    if game_id not in games:
        return
    
    game = games[game_id]
    state = game['game_state']
    
    # Speichere aktive Spieler für diese Runde (nur die, die zu Beginn dabei sind)
    state['active_players'] = game['players'].copy()
    
    # Wähle Card Czar (rotiert)
    players = state['active_players']  # Verwende active_players statt game['players']
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
    
    # Setze Timer für Antwort-Phase BEVOR Clients informiert werden
    answer_time = game['settings'].get('answer_time', 60)
    state['timer'] = answer_time
    
    # Sende Rundeninformationen an alle aktiven Spieler
    for player in state['active_players']:
        player_data = {
            'czar': czar,
            'question': current_question,
            'hand': state['player_hands'].get(player, []),
            'scores': state['player_scores'],
            'is_czar': player == czar,
            'answer_time': answer_time,
            'win_score': game['settings'].get('win_score', 10),
            'max_rounds': game['settings'].get('max_rounds', 50),
            'current_round': len(state['round_history']) + 1
        }
        
        # Finde SID des Spielers
        for username, user_data in users.items():
            if username == player and user_data.get('game_id') == game_id:
                socketio.emit('round_started', player_data, room=user_data['sid'])
                break
    
    # Sende Read-Only Ansicht an Spectators
    game = games.get(game_id)
    if game and 'spectators' in game:
        for spectator in game['spectators']:
            spectator_data = {
                'czar': czar,
                'question': current_question,
                'hand': [],  # Spectators haben keine Karten
                'scores': state['player_scores'],
                'is_czar': False,
                'is_spectator': True,
                'answer_time': answer_time,
                'win_score': game['settings'].get('win_score', 10),
                'max_rounds': game['settings'].get('max_rounds', 50),
                'current_round': len(state['round_history']) + 1
            }
            
            # Finde SID des Spectators
            for username, user_data in users.items():
                if username == spectator and user_data.get('game_id') == game_id:
                    socketio.emit('round_started', spectator_data, room=user_data['sid'])
                    break

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
    
    # Spectators dürfen keine Antworten abgeben
    if users[username].get('is_spectator', False):
        emit('error', {'message': 'Zuschauer können nicht mitspielen'})
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
        'total_players': len(state['active_players']) - 1  # -1 für Czar
    }, room=game_id)
    
    # Prüfe ob alle VERBUNDENEN aktiven Spieler abgegeben haben
    czar = state['active_players'][state['current_czar_index']]
    connected_players = [p for p in state['active_players'] if p != czar and p in users and users[p].get('status') == 'connected']
    connected_submitted = [p for p in connected_players if p in state['submitted_answers']]
    
    if len(connected_players) > 0 and len(connected_submitted) == len(connected_players):
        # Alle verbundenen Spieler haben abgegeben
        # Auto-submit für disconnected Spieler
        for player in state['active_players']:
            if player != czar and player not in state['submitted_answers']:
                # Spieler ist disconnected - wähle zufällige Karten
                hand = state['player_hands'].get(player, [])
                num_blanks = state['current_question']['num_blanks']
                if len(hand) >= num_blanks:
                    random_indices = random.sample(range(len(hand)), num_blanks)
                    state['submitted_answers'][player] = random_indices
                    print(f"Auto-submitted for disconnected player {player}: {random_indices}", flush=True)
        
        # Alle haben abgegeben (inkl. auto-submit), starte Voting-Phase
        start_voting_phase(game_id)
        
        # Alle haben abgegeben (inkl. auto-submit), starte Voting-Phase
        start_voting_phase(game_id)

def start_voting_phase(game_id):
    """Startet die Voting-Phase"""
    if game_id not in games:
        return
    
    game = games[game_id]
    state = game['game_state']
    
    state['round_phase'] = 'voting'
    
    # Czar-Zeit aus Settings
    czar_time = game['settings'].get('czar_time', 30)
    state['timer'] = czar_time
    
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
    
    # Verwende die zentrale Funktion
    process_winner_selection(game_id, winner_index)

def refill_hands(game_id):
    """Füllt Spielerhände wieder auf"""
    if game_id not in games:
        return
    
    game = games[game_id]
    state = game['game_state']
    max_cards = game['settings']['max_cards']
    
    for player in game['players']:
        # Stelle sicher, dass Spieler eine Hand hat (für neue Spieler)
        if player not in state['player_hands']:
            state['player_hands'][player] = []
        if player not in state['player_scores']:
            state['player_scores'][player] = 0
            
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
    
    # Hole die gewinnenden Antworten der letzten Runde
    winner_answer_indices = state.get('submitted_answers', {}).get(winner, [])
    winner_answers = [state['player_hands'][winner][i] for i in winner_answer_indices if i < len(state['player_hands'].get(winner, []))]
    
    # Sende Spielende-Info mit zusätzlichen Daten
    socketio.emit('game_ended', {
        'winner': winner,
        'final_scores': state['player_scores'],
        'last_question': state.get('current_question'),
        'last_czar': state['active_players'][state['current_czar_index']] if state.get('active_players') else None,
        'winner_answers': winner_answers,
        'round_history': state.get('round_history', [])
    }, room=game_id)
    
    # Reset Spiel
    game['started'] = False
    game['game_state'] = None
    broadcastPublicGames()

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
    
    # Informiere alle Spieler mit aktuellem Timer
    socketio.emit('game_paused', {'time_left': state.get('timer', -1)}, room=game_id)

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
    
    # Informiere alle Spieler - Timer läuft automatisch weiter durch universal_timer_task
    socketio.emit('game_resumed', {
        'time_left': state.get('timer', -1)
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
    broadcastPublicGames()

if __name__ == '__main__':
    print("Starte Server...", flush=True)
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=False)

