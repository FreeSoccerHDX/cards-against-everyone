from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import time
import eventlet
from questions import CARDS_QUESTIONS
from answers import CARDS_ANSWERS
from game import Game
import re
import traceback

app = Flask(__name__)
app.config['SECRET_KEY'] = 'cards-against-everyone-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

# Datenstrukturen
users: dict[str, dict] = {}  # {username: {sid: str, last_seen: float, game_id: str}}
users_by_sid: dict[str, str] = {}  # {sid: username}
games: dict[str, Game] = {}  # {game_id: Game}
disconnect_timers: dict[str, float] = {}  # {username: timestamp of disconnect}
global_timer_task: eventlet.greenthread = None  # Globaler Timer-Task
timer_started: bool = False  # Flag ob Timer bereits gestartet wurde

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
                if not game.is_game_started():
                    continue
                            
                # Pausierte Spiele überspringen
                if game.paused:
                    continue
                
                # Timer tick
                success, message = game.timer_tick()
                if not success:
                    print(f"Fehler beim Timer-Tick für Spiel {game_id}: {message}", flush=True)
                    
                # Sende Timer-Update an Clients
                socketio.emit('timer_sync', {
                    'time_left': game.currentTimerSeconds,
                    'max_time': game.currentTimerTotalSeconds
                    }, room=game_id)
        
            eventlet.sleep(1) # sleep 1s
        except Exception as e:
            print(f"Error in universal_timer_task: {e}", flush=True)
            traceback.print_exc()
            eventlet.sleep(1)
 

def broadcastPublicGames():
    for username in users.keys():
        sid = users[username]['sid']
        socketio.emit('public_games_list', {'games': get_public_games(username)}, room=sid)

def cleanup_user(username):
    """Entfernt Benutzer nach 30 Sekunden Inaktivität"""
    if username in users:
        game_id = users[username].get('game_id')
        if game_id and game_id in games:
            game = games[game_id]
            success = game.remove_player(username)
            
            # Spiel löschen wenn kein neuer owner -> kein Spieler mehr da
            if game.owner == None:
                del games[game_id]
            else:
                # Informiere andere Spieler
                socketio.emit('player_left', {
                    'username': username,
                    'game': game.get_socket_game_data(include_history=True)
                }, room=game_id)
        
        del users[username]
        if username in disconnect_timers:
            del disconnect_timers[username]

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('funny_name_used')
def handle_funny_name_used(data):
    names = data.get('names', [])
    name = None

    # Überprüfe, ob der Name verfügbar ist
    for n in names:
        available = True
        if n in users and users[n].get('status', 'connected') == 'connected':
            available = False
        if available:
            name = n
            break

    # Sende Antwort zurück an den Client
    emit('funny_name_used_response', {
        'name': name,
        'available': name is not None
    })


@socketio.on('ping')
def handle_ping(data):
    emit('pong', {
        "serverTime": time.time(), 
        "startTime": data.get('startTime', -1),
        "pingId": data.get('pingId', -1)
        })
    
    # update client last seen + game-player_status if exist
    username = users_by_sid.get(request.sid, None)
    if username and username in users:
        users[username]['status'] = 'connected'
        users[username]['last_seen'] = time.time()
        game_id = users[username].get('game_id')
        if game_id and game_id in games:
            game = games[game_id]
            game.mark_player_connection_status(username, 'connected')

@socketio.on('connect')
def handle_connect():
    global global_timer_task, timer_started
    print(f'Client connected: {request.sid}', flush=True)
    users_by_sid[request.sid] = None  # Noch kein Username zugewiesen
    
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
    username = users_by_sid.get(request.sid, None)
    users_by_sid.pop(request.sid, None)
    
    if username:
        # Markiere als disconnecting
        users[username]['status'] = 'disconnecting'
        
        # Informiere Mitspieler über Status-Änderung
        game_id = users[username].get('game_id')
        if game_id and game_id in games:
            game = games[game_id]
            game.mark_player_connection_status(username, 'disconnecting')
        
        disconnect_timers[username] = time.time()

@socketio.on('set_username')
def handle_set_username(data):
    username = data.get('username', '').strip()
    
    if not username:
        emit('username_error', {'message': 'Bitte gib einen Namen ein'})
        return
    
    # Bereinige Username: Ersetze mehrfache Leerzeichen durch ein einzelnes
    username = re.sub(r'\s+', ' ', username).strip()
    
    # Prüfe Länge
    if len(username) < 2:
        emit('username_error', {'message': 'Der Name muss mindestens 2 Zeichen lang sein'})
        return
    
    if len(username) > 30:
        emit('username_error', {'message': 'Der Name darf maximal 30 Zeichen lang sein (aktuell: ' + str(len(username)) + ')'})
        return
    
    # Prüfe ob Name bereits existiert und Spieler verbunden ist
    if username in users:
        # Wenn es der gleiche Benutzer ist (Reconnect)
        if users[username]['sid'] == request.sid:
            emit('username_set', {'username': username})
            users_by_sid[request.sid] = username
            return
        
        # Prüfe ob der andere Spieler noch verbunden ist
        user_status = users[username].get('status', 'connected')
        if user_status == 'connected':
            emit('username_error', {'message': 'Dieser Name ist bereits vergeben'})
            return
    
    # Registriere Benutzer
    users[username] = {
        'sid': request.sid,
        'last_seen': time.time(),
        'game_id': None,
        'status': 'connected'
    }
    users_by_sid[request.sid] = username
    
    # Lösche eventuellen Timer
    if username in disconnect_timers:
        del disconnect_timers[username]
    
    emit('username_set', {'username': username})

@socketio.on('reconnect_user')
def handle_reconnect(data):
    username = data.get('username', '').strip()
    
    if username in users:
        # check connection status
        user_status = users[username].get('status')
        if user_status == 'connected':
            emit('reconnected', {
                'success': False,
                'reload': True,
                'message': 'Bereits verbunden'})
            return

        # Aktualisiere SID
        users[username]['sid'] = request.sid
        users[username]['last_seen'] = time.time()
        users[username]['status'] = 'connected'
        users_by_sid[request.sid] = username
        
        # Lösche potenziellen Timer
        if username in disconnect_timers:
            del disconnect_timers[username]

        game_id = users[username].get('game_id')
        hasGame = game_id is not None and game_id in games

        emit('username_set', {'username': username, 'hasGame': hasGame})
        
        if hasGame:
            # Informiere über Reconnect
            game = games[game_id]
            game.mark_player_connection_status(username, 'connected')

            # Trete SocketIO-Raum wieder bei um updates zu erhalten -> globale method von flask_socketio
            join_room(game_id)
            
            game = games[game_id]
            
            emit('reconnected', {
                'success': True,
                'game': game.get_socket_game_data(current_player_cards=username, include_history=True)
            })
        else:
            emit('reconnected', {
                'success': False
                })
    else:
        emit('reconnected', {
            'success': False,
            'reload': True,
            'message': 'Benutzername nicht gefunden'
        })

@socketio.on('create_game')
def handle_create_game(data):
    success,username,game = get_current_data(need_game=False)
    if not success:
        return
    
    game_name = data.get('name', username + "'s Spiel").strip()
    is_public = data.get('is_public', True)
    password = data.get('password', '').strip()
    
    game = Game(socketio, users, username, game_name, isPublicVisible=is_public, password=password)
    game_id = game.game_id
    games[game_id] = game
    
    users[username]['game_id'] = game_id
    join_room(game_id)
    
    emit('game_created', game.get_socket_game_data())
    # Aktualisiere Lobby für alle
    broadcastPublicGames()

@socketio.on('get_public_games')
def handle_get_public_games():
    success,username,game = get_current_data(need_game=False)
    if not success:
        return
    emit('public_games_list', {'games': get_public_games(username)})

@socketio.on('get_game_info_link_join')
def handle_get_game_info(data):
    success,username,game = get_current_data(need_game=True)
    if not success:
        emit('game_info_link_join_error', {'message': 'Spiel nicht gefunden'})
        return
    
    emit('game_info_link_join', {
        'id': game.game_id,
        'name': game.settings["gameName"],
        'has_password': bool(game.settings["password"]),
        'started': game.is_game_started()
    })

def get_public_games(username=None):
    """Gibt alle öffentlichen Spiele zurück"""
    public_games = []
    for game_id, game in games.items():
        pending = game.is_pending_player(username)
        if pending or ((not game.is_game_started() and game.settings["publicVisible"]) or (game.is_game_started() and game.settings["publicVisibleDuringGame"])):
            public_games.append({
                'id': game_id,
                'is_pending': pending,
                'name': game.settings["gameName"],
                'players': len(game.active_players),
                'has_password': bool(game.settings["password"])
            })
    return public_games

@socketio.on('get_game_state')
def handle_get_game_state():
    """Sendet den aktuellen Spielzustand an den anfragenden Client"""
    success,username,game = get_current_data(need_game=True)
    if not success:
        return
    
    emit('game_state_update', game.get_socket_game_data(current_player_cards=username, include_history=True))

@socketio.on('join_game')
def handle_join_game(data):
    success,username,game = get_current_data(need_game=False)
    if not success:
        return
    
    game_id = data.get('game_id')
    password = data.get('password', '')
    is_spectator = data.get('is_spectator', False)  # Ob als Zuschauer beigetreten wird
    
    if game_id not in games:
        emit('error', {'message': 'Spiel nicht gefunden'})
        return
    
    game = games[game_id]
    
    # Prüfe Passwort
    if game.settings.get("password") and game.settings["password"] != password:
        emit('error', {'message': 'Falsches Passwort'})
        return
    
    success, message = game.add_player(username, isSpectator=is_spectator)
    if success:
        users[username]['game_id'] = game_id
        join_room(game_id)
    
        emit('game_joined', game.get_socket_game_data(current_player_cards=username, include_history=True))
        
        # Informiere andere Spieler
        emit('player_joined', {
            'username': username,
            'is_spectator': is_spectator,
            'game': game.get_socket_game_data(include_history=True)
        }, room=game_id, include_self=False)

    else:
        emit('error', {'message': message})
            
    # Aktualisiere Lobby
    broadcastPublicGames()

@socketio.on('leave_game')
def handle_leave_game():
    success,username,game = get_current_data(need_game=True)
    if not success:
        return
    
    game.remove_player(username)
    
    users[username]['game_id'] = None
    leave_room(game.game_id) # entferne aus SocketIO-Raum
    
    # Spiel löschen wenn leer
    if game.owner == None:
        del games[game.game_id]
    else:
        # Informiere andere Spieler
        emit('player_left', {
            'username': username,
            'game': game.get_socket_game_data(include_history=True)
        }, room=game.game_id)
    
    emit('left_game', {})
    # Aktualisiere Lobby
    broadcastPublicGames()


# return succes,username,game
def get_current_data(need_game):
    """Hilfsfunktion um aktuellen Zustand des Sockets zu bekommen"""
    username = users_by_sid.get(request.sid, None)
    if not username:
        emit('error', {'message': 'Nicht angemeldet'})
        return False, None, None
    if not need_game:
        return True, username, None
    else:
        game_id = users[username].get('game_id')
        if not game_id or game_id not in games:
            emit('error', {'message': 'Nicht in einem Spiel'})
            return False, username, None
        
        game = games[game_id]
        return True, username, game
    


@socketio.on('kick_player')
def handle_kick_player(data):
    success,kicker,game = get_current_data(need_game=True)
    if not success:
        return
    
    # Nur Creator kann kicken
    if game.owner != kicker:
        emit('error', {'message': 'Nur der Ersteller kann Spieler kicken'})
        return
    
    # Spiel darf nicht gestartet sein
    if game.is_game_started():
        emit('error', {'message': 'Spieler können während des Spiels nicht gekickt werden'})
        return
    
    kicked_user = data.get('username')

    # Creator kann sich nicht selbst kicken
    if kicked_user == kicker:
        emit('error', {'message': 'Du kannst dich nicht selbst kicken'})
        return
    
    # Prüfe ob in players oder spectators
    if kicked_user in game.active_players or kicked_user in game.spectators:
        success = game.remove_player(kicked_user)
        if success:
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
                'game': game.get_socket_game_data(include_history=True)
            }, room=game.game_id)
            
            broadcastPublicGames()

@socketio.on('toggle_role')
def handle_toggle_role():
    success,username,game = get_current_data(need_game=True)
    if not success:
        return
    
    # Spiel darf nicht gestartet sein
    if game.is_game_started():
        emit('error', {'message': 'Rolle kann während des Spiels nicht gewechselt werden'})
        return
    
    was_spectator = username in game.spectators
    success, message = game.toggle_role(username)
    
    if success:    
        # Informiere alle im Raum
        emit('role_changed', {
            'username': username,
            'role': 'Spieler' if was_spectator else 'Zuschauer',
            'game': game.get_socket_game_data(),
        }, room=game.game_id)
        
        emit('success', {'message': f'Du bist jetzt {"Spieler" if was_spectator else "Zuschauer"}'})
    else:
        emit('error', {'message': 'Rollenwechsel fehlgeschlagen: ' + message})

@socketio.on('force_role')
def handle_force_role(data):
    """Creator erzwingt Rollenwechsel für anderen Spieler"""
    success,creator,game = get_current_data(need_game=True)
    if not success:
        return
    
    # Nur Creator kann Rollen erzwingen
    if game.owner != creator:
        emit('error', {'message': 'Nur der Ersteller kann Rollen ändern'})
        return
    
    # Spiel darf nicht gestartet sein
    if game.is_game_started():
        emit('error', {'message': 'Rolle kann während des Spiels nicht gewechselt werden'})
        return
    
    target_username = data.get('username')
    if not target_username or target_username not in users:
        return
    
    # Creator kann sich selbst nicht verschieben (dafür toggle_role nutzen)
    if target_username == creator:
        emit('error', {'message': 'Nutze deinen eigenen Toggle-Button um deine Rolle zu ändern'})
        return
    
    was_spectator = target_username in game.spectators
    
    if game.toggle_role(target_username):    
        # Informiere alle im Raum
        emit('role_changed', {
            'username': target_username,
            'role': 'Spieler' if was_spectator else 'Zuschauer',
            'game': game.get_socket_game_data(),
            'forced_by': creator
        }, room=game.game_id)
        
        emit('success', {'message': f'Du bist jetzt {"Spieler" if was_spectator else "Zuschauer"}'})
    else:
        emit('error', {'message': 'Rollenwechsel fehlgeschlagen'})

@socketio.on('update_settings')
def handle_update_settings(settings):
    success,username,game = get_current_data(need_game=True)
    if not success:
        return
    
    # Nur Ersteller kann Einstellungen ändern
    if game.owner != username:
        emit('error', {'message': 'Nur der Ersteller kann Einstellungen ändern'})
        return
    
    # Aktualisiere Einstellungen
    game.updateSettings(settings)
    
    # Informiere alle Spieler im Raum
    game.send_socket_game_update_for_all(channel='settings_updated')
    
    # Aktualisiere Lobby
    broadcastPublicGames()

@socketio.on('start_game')
def handle_start_game():
    success,username,game = get_current_data(need_game=True)
    if not success:
        return
    
    # Nur Ersteller kann Spiel starten
    if game.owner != username:
        emit('error', {'message': 'Nur der Ersteller kann das Spiel starten'})
        return
    
    # Zähle nur aktive Spieler (keine Spectators)
    active_player_count = len(game.active_players)
    if active_player_count < 3:
        emit('error', {'message': 'Mindestens 3 aktive Spieler erforderlich (Zuschauer zählen nicht)'})
        return
    
    if game.start_game():
        socketio.emit('info', {'message': f'Spiel gestartet'}, room=game.game_id)
        game.send_socket_game_update_for_all(channel='game_started')
        
    # Aktualisiere Lobby in jedem Fall
    broadcastPublicGames()
    
@socketio.on('submit_answers')
def handle_submit_answers(data):
    """Spieler gibt Antworten ab"""
    success,username,game = get_current_data(need_game=True)
    if not success:
        return
    
    # Validiere Antworten
    answer_indices = data.get('answer_indices', [])
    num_blanks = game.current_black_card["num_blanks"]
    
    if len(answer_indices) != num_blanks:
        emit('error', {'message': f'Bitte wähle genau {num_blanks} Karte(n)'})
        return
    
    success,error = game.submit_white_cards(username, answer_indices)
    if not success:
        emit('error', {'message': error})
        return
    
    # Benachrichtige alle über Abgabe
    socketio.emit('player_submitted', {
        'username': username,
        'czar': game.czar,
        'players': game.active_players,
        'spectators': game.spectators,
        'submitted_count': len(game.submitted_white_cards),
        'total_players': len(game.active_players) - 1  # -1 für Czar
    }, room=game.game_id)

    # Prüfe ob alle VERBUNDENEN aktiven Spieler abgegeben haben
    czar = game.czar
    connected_players = [p for p in game.active_players if p != czar and p in users and users[p].get('status') == 'connected']
    connected_submitted = [p for p in connected_players if p in game.submitted_white_cards]
    
    if len(connected_players) > 0 and len(connected_submitted) == len(connected_players):
        # Alle verbundenen Spieler haben abgegeben, es fehlen nur noch die disconnected Spieler
        # Auto-submit für disconnected Spieler falls nötig
        game.autosubmit_white_cards()

    # Sende vollständigen aktuellen Spielzustand an alle
    game.send_socket_game_update_for_all(channel='game_state_update', include_history=True)

@socketio.on('vote_winner')
def handle_vote_winner(data):
    """Card Czar wählt Gewinner"""
    success,username,game = get_current_data(need_game=True)
    if not success:
        return
    
    winner_index = data.get('winner_index')
    playerMapping = game.player_mapping

    if winner_index is None:
        emit('error', {'message': 'Kein Index angegeben'})
        return

    if not isinstance(winner_index, int):
        emit('error', {'message': 'Ungültiger Index'})
        return
    
    if winner_index < 0 or winner_index >= len(playerMapping):
        emit('error', {'message': 'Index außerhalb des gültigen Bereichs'})
        return
    
    success,error = game.choose_winner(playerMapping[winner_index], username)
    
    if not success:
        emit('error', {'message': error})
        return
    
    game.send_socket_game_update_for_all(channel='game_state_update', include_history=True)


@socketio.on('pause_game')
def handle_pause_game():
    success,username,game = get_current_data(need_game=True)
    if not success:
        return
    
    # Nur Ersteller kann pausieren
    if game.owner != username:
        emit('error', {'message': 'Nur der Ersteller kann das Spiel pausieren'})
        return
    
    if not game.is_game_started():
        emit('error', {'message': 'Das Spiel wurde noch nicht gestartet'})
        return
    
    if game.paused:
        emit('error', {'message': 'Das Spiel ist bereits pausiert'})
        return
    
    game.paused = True
    
    # Informiere alle Spieler mit aktuellem Timer
    socketio.emit('game_paused', {'time_left': game.currentTimerSeconds}, room=game.game_id)

@socketio.on('resume_game')
def handle_resume_game():
    success,username,game = get_current_data(need_game=True)
    if not success:
        return
    
    # Nur Ersteller kann fortsetzen
    if game.owner != username:
        emit('error', {'message': 'Nur der Ersteller kann das Spiel fortsetzen'})
        return
    
    if not game.is_game_started():
        emit('error', {'message': 'Das Spiel wurde noch nicht gestartet'})
        return
    
    if not game.paused:
        emit('error', {'message': 'Das Spiel ist nicht pausiert'})
        return
    
    game.paused = False
    
    # Informiere alle Spieler - Timer läuft automatisch weiter durch universal_timer_task
    socketio.emit('game_resumed', {'time_left': game.currentTimerSeconds}, room=game.game_id)

@socketio.on('reset_to_lobby')
def handle_reset_to_lobby():
    success,username,game = get_current_data(need_game=True)
    if not success:
        return
    
    # Nur Ersteller kann zurück zur Lobby
    if game.owner != username:
        emit('error', {'message': 'Nur der Ersteller kann das Spiel zurücksetzen'})
        return
    
    # Reset Spiel
    game.reset_to_lobby()
    
    # Informiere alle Spieler
    game.send_socket_game_update_for_all(channel='game_reset_to_lobby', include_history=True)
    broadcastPublicGames()

if __name__ == '__main__':
    print("Starte Server...", flush=True)
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)

