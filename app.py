from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import os
import re
import secrets
import time
import traceback
from game import Game, BOT_NAME_PREFIX

DEBUG = os.environ.get('DEBUG', '0') == '1'
# Benutzer ohne Spiel werden nach so vielen Sekunden ohne Verbindung entfernt
DISCONNECT_CLEANUP_SECONDS = 30

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
socketio = SocketIO(app, cors_allowed_origins="*")

# Datenstrukturen
users: dict[str, dict] = {}  # {username: {sid, token, game_id, status, disconnected_at, last_seen}}
users_by_token: dict[str, str] = {}  # {session_token: username}
users_by_sid: dict[str, str] = {}  # {sid: username}
games: dict[str, Game] = {}  # {game_id: Game}
timer_started: bool = False  # Flag ob Timer bereits gestartet wurde


def as_dict(data):
    return data if isinstance(data, dict) else {}


# ########################################
#       Hintergrund-Timer
# ########################################

def universal_timer_task():
    """Universeller Timer der alle Spiele durchläuft und Timer aktualisiert"""
    print("Universal Timer Task gestartet", flush=True)
    while True:
        try:
            tick_all(time.time())
        except Exception as e:
            print(f"Error in universal_timer_task: {e}", flush=True)
            traceback.print_exc()
        socketio.sleep(1)


def tick_all(now):
    # Benutzer ohne Spiel nach 30 Sekunden ohne Verbindung entfernen.
    # Benutzer in einem Spiel behalten ihren Platz (AFK), bis sie gehen oder gekickt werden.
    for username, user in list(users.items()):
        if user['status'] == 'disconnecting' and get_user_game(username) is None \
                and now - user['disconnected_at'] >= DISCONNECT_CLEANUP_SECONDS:
            print(f"Bereinige Benutzer nach {DISCONNECT_CLEANUP_SECONDS} Sekunden ohne Verbindung: {username}", flush=True)
            delete_user(username)

    for game_id, game in list(games.items()):
        try:
            if game.housekeeping(now):
                print(f"Lösche Spiel ohne verbundene Spieler: {game_id}", flush=True)
                delete_game(game_id)
                continue

            # Nur laufende, nicht pausierte Spiele
            if not game.is_game_started() or game.paused:
                continue

            success, message = game.timer_tick()
            if not success:
                print(f"Fehler beim Timer-Tick für Spiel {game_id}: {message}", flush=True)

            # Sende Timer-Update an Clients
            socketio.emit('timer_sync', {
                'time_left': game.currentTimerSeconds,
                'max_time': game.currentTimerTotalSeconds
            }, room=game_id)
        except Exception as e:
            # Ein fehlerhaftes Spiel darf die anderen nicht blockieren
            print(f"Fehler in Spiel {game_id}: {e}", flush=True)
            traceback.print_exc()


# ########################################
#       Helpers
# ########################################

def get_user_game(username):
    """Gibt das Spiel des Benutzers zurück, falls er noch Mitglied ist"""
    user = users.get(username)
    if not user:
        return None
    game = games.get(user.get('game_id'))
    if game is None or not game.is_member(username):
        user['game_id'] = None
        return None
    return game


def delete_user(username):
    user = users.pop(username, None)
    if not user:
        return
    users_by_token.pop(user['token'], None)
    if users_by_sid.get(user['sid']) == username:
        users_by_sid[user['sid']] = None


def delete_game(game_id):
    game = games.pop(game_id, None)
    if not game:
        return
    for member in game.members():
        if member in users and users[member]['game_id'] == game_id:
            users[member]['game_id'] = None
    broadcastPublicGames()


def leave_current_game(username):
    """Entfernt den Benutzer aus seinem aktuellen Spiel"""
    game = get_user_game(username)
    users[username]['game_id'] = None
    if not game:
        return

    game.remove_player(username)
    leave_room(game.game_id, sid=users[username]['sid'], namespace='/')

    # Spiel löschen wenn keine Menschen mehr drin sind
    if not game.human_members():
        games.pop(game.game_id, None)
    else:
        # Informiere andere Spieler
        game.send_socket_game_update_for_all(channel='player_left', extra={'username': username})
    broadcastPublicGames()


def broadcastPublicGames():
    for username, user in users.items():
        if user['status'] == 'connected':
            socketio.emit('public_games_list', {'games': get_public_games(username)}, room=user['sid'])


def get_public_games(username=None):
    """Gibt alle öffentlichen Spiele zurück"""
    public_games = []
    for game_id, game in games.items():
        pending = game.is_pending_player(username)
        started = game.is_game_started()
        visible = game.settings["publicVisibleDuringGame"] if started else game.settings["publicVisible"]
        if pending or visible:
            public_games.append({
                'id': game_id,
                'is_pending': pending,
                'name': game.settings["gameName"],
                'players': len(game.active_players) + len(game.pending_players),
                'started': started,
                'has_password': bool(game.settings["password"])
            })
    return public_games


# return success,username,game
def get_current_data(need_game):
    """Hilfsfunktion um aktuellen Zustand des Sockets zu bekommen"""
    username = users_by_sid.get(request.sid, None)
    if not username or username not in users:
        emit('error', {'message': 'Nicht angemeldet'})
        return False, None, None
    if not need_game:
        return True, username, None

    game = get_user_game(username)
    if not game:
        emit('error', {'message': 'Nicht in einem Spiel'})
        return False, username, None
    return True, username, game


# ########################################
#       Routes / Verbindung
# ########################################

@app.route('/')
def index():
    return render_template('index.html')


@socketio.on('connect')
def handle_connect():
    global timer_started
    print(f'Client connected: {request.sid}', flush=True)
    users_by_sid[request.sid] = None  # Noch kein Username zugewiesen

    # Starte Timer beim ersten Connect
    if not timer_started:
        timer_started = True
        print("Starte Universal Timer Task...", flush=True)
        socketio.start_background_task(universal_timer_task)


@socketio.on('disconnect')
def handle_disconnect(*args):
    print(f'Client disconnected: {request.sid}', flush=True)
    username = users_by_sid.pop(request.sid, None)

    # Ignorieren, wenn der Benutzer inzwischen mit einem neuen Socket verbunden ist
    if not username or username not in users or users[username]['sid'] != request.sid:
        return

    users[username]['status'] = 'disconnecting'
    users[username]['disconnected_at'] = time.time()

    # Informiere Mitspieler über Status-Änderung
    game = get_user_game(username)
    if game:
        game.mark_player_connection_status(username, 'disconnecting', now=time.time())


@socketio.on('ping')
def handle_ping(data):
    data = as_dict(data)
    emit('pong', {
        "serverTime": time.time(),
        "startTime": data.get('startTime', -1),
        "pingId": data.get('pingId', -1)
        })

    username = users_by_sid.get(request.sid, None)
    if username and username in users:
        users[username]['last_seen'] = time.time()


@socketio.on('funny_name_used')
def handle_funny_name_used(data):
    names = as_dict(data).get('names', [])
    if not isinstance(names, list):
        names = []

    # Erster Name, der noch nicht vergeben ist
    name = next((n for n in names if isinstance(n, str) and n not in users), None)

    emit('funny_name_used_response', {
        'name': name,
        'available': name is not None
    })


@socketio.on('set_username')
def handle_set_username(data):
    username = as_dict(data).get('username', '')
    if not isinstance(username, str):
        username = ''

    # Bereinige Username: Ersetze mehrfache Leerzeichen durch ein einzelnes
    username = re.sub(r'\s+', ' ', username).strip()

    if not username:
        emit('username_error', {'message': 'Bitte gib einen Namen ein'})
        return

    if len(username) < 2:
        emit('username_error', {'message': 'Der Name muss mindestens 2 Zeichen lang sein'})
        return

    if len(username) > 30:
        emit('username_error', {'message': 'Der Name darf maximal 30 Zeichen lang sein (aktuell: ' + str(len(username)) + ')'})
        return

    if username.startswith(BOT_NAME_PREFIX.split(' ')[0]):
        emit('username_error', {'message': 'Dieser Name ist für Bots reserviert'})
        return

    current = users_by_sid.get(request.sid)
    if current == username:
        user = users[username]
        emit('username_set', {'username': username, 'token': user['token'], 'hasGame': get_user_game(username) is not None})
        return

    # Name bleibt reserviert, solange der Benutzer existiert (auch wenn er gerade AFK ist)
    if username in users:
        emit('username_error', {'message': 'Dieser Name ist bereits vergeben'})
        return

    # Dieser Socket hatte schon einen anderen Namen -> alten Benutzer freigeben
    if current and current in users:
        leave_current_game(current)
        delete_user(current)

    token = secrets.token_urlsafe(32)
    users[username] = {
        'sid': request.sid,
        'token': token,
        'last_seen': time.time(),
        'disconnected_at': None,
        'game_id': None,
        'status': 'connected'
    }
    users_by_token[token] = username
    users_by_sid[request.sid] = username

    emit('username_set', {'username': username, 'token': token, 'hasGame': False})


@socketio.on('reconnect_user')
def handle_reconnect(data):
    token = as_dict(data).get('token')
    username = users_by_token.get(token) if isinstance(token, str) else None

    if not username or username not in users:
        emit('reconnected', {
            'success': False,
            'reload': True,
            'message': 'Sitzung abgelaufen – bitte melde dich neu an'
        })
        return

    user = users[username]
    game = get_user_game(username)

    # Alter Socket (anderer Tab oder tote Verbindung) wird abgelöst
    old_sid = user['sid']
    if old_sid != request.sid:
        if users_by_sid.get(old_sid) == username:
            users_by_sid[old_sid] = None
            socketio.emit('session_taken_over', {
                'message': 'Das Spiel wurde in einem anderen Tab geöffnet'
            }, room=old_sid)
        if game:
            leave_room(game.game_id, sid=old_sid, namespace='/')

    user['sid'] = request.sid
    user['last_seen'] = time.time()
    user['status'] = 'connected'
    user['disconnected_at'] = None
    users_by_sid[request.sid] = username

    emit('username_set', {'username': username, 'token': token, 'hasGame': game is not None})

    if game:
        join_room(game.game_id)
        game.mark_player_connection_status(username, 'connected')
        for message in game.pending_notices.pop(username, []):
            emit('info', {'message': message})
        emit('reconnected', {
            'success': True,
            'game': game.get_socket_game_data(current_playerName=username)
        })
    else:
        emit('reconnected', {'success': True, 'game': None})


@socketio.on('logout')
def handle_logout():
    username = users_by_sid.get(request.sid)
    if username and username in users:
        leave_current_game(username)
        delete_user(username)
    users_by_sid[request.sid] = None
    emit('logged_out', {})


# ########################################
#       Lobby
# ########################################

@socketio.on('create_game')
def handle_create_game(data):
    success, username, _ = get_current_data(need_game=False)
    if not success:
        return
    data = as_dict(data)

    # Vorheriges Spiel verlassen
    leave_current_game(username)

    game_name = data.get('name')
    if not isinstance(game_name, str) or not game_name.strip():
        game_name = username + "'s Spiel"
    password = data.get('password', '')
    if not isinstance(password, str):
        password = ''

    game = Game(socketio, users, username, game_name[:30], isPublicVisible=bool(data.get('is_public', True)), password=password)
    games[game.game_id] = game

    users[username]['game_id'] = game.game_id
    join_room(game.game_id)

    emit('game_created', game.get_socket_game_data(current_playerName=username))
    # Aktualisiere Lobby für alle
    broadcastPublicGames()


@socketio.on('get_public_games')
def handle_get_public_games():
    success, username, _ = get_current_data(need_game=False)
    if not success:
        return
    emit('public_games_list', {'games': get_public_games(username)})


@socketio.on('get_game_info_link_join')
def handle_get_game_info(data):
    success, _, _ = get_current_data(need_game=False)
    if not success:
        return

    game_id = as_dict(data).get('game_id')
    game = games.get(game_id) if isinstance(game_id, str) else None
    if not game:
        emit('game_info_link_join_error', {'message': 'Spiel nicht gefunden'})
        return

    emit('game_info_link_join', {
        'id': game.game_id,
        'name': game.settings["gameName"],
        'has_password': bool(game.settings["password"]),
        'started': game.is_game_started()
    })


@socketio.on('get_game_state')
def handle_get_game_state():
    """Sendet den aktuellen Spielzustand an den anfragenden Client"""
    success, username, game = get_current_data(need_game=True)
    if not success:
        return

    emit('game_state_update', game.get_socket_game_data(current_playerName=username))


@socketio.on('join_game')
def handle_join_game(data):
    success, username, _ = get_current_data(need_game=False)
    if not success:
        return
    data = as_dict(data)

    game_id = data.get('game_id')
    password = data.get('password', '')
    is_spectator = bool(data.get('is_spectator', False))  # Ob als Zuschauer beigetreten wird

    game = games.get(game_id) if isinstance(game_id, str) else None
    if not game:
        emit('error', {'message': 'Spiel nicht gefunden'})
        return

    already_member = game.is_member(username)

    # Prüfe Passwort (nicht bei Mitgliedern, die nur zurückkehren)
    if not already_member and game.settings["password"] and game.settings["password"] != password:
        emit('error', {'message': 'Falsches Passwort'})
        return

    # Vorheriges Spiel verlassen
    current_game = get_user_game(username)
    if current_game and current_game is not game:
        leave_current_game(username)

    success, message = game.add_player(username, isSpectator=is_spectator)
    if not success:
        emit('error', {'message': message})
        broadcastPublicGames()
        return

    users[username]['game_id'] = game.game_id
    join_room(game.game_id)

    emit('game_joined', game.get_socket_game_data(current_playerName=username))
    if game.is_game_started() and username in game.pending_players:
        emit('info', {'message': 'Das Spiel läuft bereits – du steigst in der nächsten Runde ein'})

    # Informiere alle Spieler
    if not already_member:
        game.send_socket_game_update_for_all(channel='player_joined', extra={
            'username': username,
            'is_spectator': is_spectator,
        })

    # Aktualisiere Lobby
    broadcastPublicGames()


@socketio.on('leave_game')
def handle_leave_game():
    success, username, _ = get_current_data(need_game=True)
    if not success:
        return

    leave_current_game(username)
    emit('left_game', {})


# ########################################
#       Spiel-Lobby (Owner-Aktionen)
# ########################################

@socketio.on('kick_player')
def handle_kick_player(data):
    success, kicker, game = get_current_data(need_game=True)
    if not success:
        return

    # Nur Owner kann kicken
    if game.owner != kicker:
        emit('error', {'message': 'Nur der Ersteller kann Spieler kicken'})
        return

    # Spiel darf nicht gestartet sein
    if game.is_game_started():
        emit('error', {'message': 'Spieler können während des Spiels nicht gekickt werden'})
        return

    kicked_user = as_dict(data).get('username')

    # Owner kann sich nicht selbst kicken
    if kicked_user == kicker:
        emit('error', {'message': 'Du kannst dich nicht selbst kicken'})
        return

    if not isinstance(kicked_user, str) or not game.is_member(kicked_user):
        emit('error', {'message': 'Spieler nicht gefunden'})
        return

    game.remove_player(kicked_user)

    if kicked_user in users:
        users[kicked_user]['game_id'] = None
        kicked_sid = users[kicked_user]['sid']
        leave_room(game.game_id, sid=kicked_sid, namespace='/')
        socketio.emit('kicked_from_game', {
            'message': f'Du wurdest von {kicker} aus dem Spiel entfernt'
        }, room=kicked_sid)

    # Informiere alle anderen
    game.send_socket_game_update_for_all(channel='player_left', extra={'username': kicked_user})
    broadcastPublicGames()


@socketio.on('add_bot')
def handle_add_bot():
    success, username, game = get_current_data(need_game=True)
    if not success:
        return

    # Nur Owner kann Bots hinzufügen
    if game.owner != username:
        emit('error', {'message': 'Nur der Ersteller kann Bots hinzufügen'})
        return

    success, result = game.add_bot()
    if not success:
        emit('error', {'message': result})
        return

    game.send_socket_game_update_for_all(channel='player_joined', extra={
        'username': result,
        'is_spectator': False,
    })
    broadcastPublicGames()


@socketio.on('toggle_role')
def handle_toggle_role():
    success, username, game = get_current_data(need_game=True)
    if not success:
        return

    success, message = game.toggle_role(username)
    if not success:
        emit('error', {'message': 'Rollenwechsel fehlgeschlagen: ' + message})
        return

    game.send_socket_game_update_for_all(channel='role_changed', extra={
        'username': username,
        'role': message,
    })


@socketio.on('force_role')
def handle_force_role(data):
    """Owner erzwingt Rollenwechsel für anderen Spieler"""
    success, owner, game = get_current_data(need_game=True)
    if not success:
        return

    # Nur Owner kann Rollen erzwingen
    if game.owner != owner:
        emit('error', {'message': 'Nur der Ersteller kann Rollen ändern'})
        return

    target_username = as_dict(data).get('username')
    if not isinstance(target_username, str) or not game.is_member(target_username):
        emit('error', {'message': 'Spieler nicht gefunden'})
        return

    # Owner kann sich selbst nicht verschieben (dafür toggle_role nutzen)
    if target_username == owner:
        emit('error', {'message': 'Nutze deinen eigenen Toggle-Button um deine Rolle zu ändern'})
        return

    success, message = game.toggle_role(target_username)
    if not success:
        emit('error', {'message': 'Rollenwechsel fehlgeschlagen: ' + message})
        return

    game.send_socket_game_update_for_all(channel='role_changed', extra={
        'username': target_username,
        'role': message,
        'forced_by': owner
    })


@socketio.on('update_settings')
def handle_update_settings(settings):
    success, username, game = get_current_data(need_game=True)
    if not success:
        return

    # Nur Owner kann Einstellungen ändern
    if game.owner != username:
        emit('error', {'message': 'Nur der Ersteller kann Einstellungen ändern'})
        return

    invalid = game.update_settings(settings)
    if invalid:
        emit('error', {'message': 'Ungültige Einstellung(en): ' + ', '.join(invalid)})

    # Informiere alle Spieler im Raum
    game.send_socket_game_update_for_all(channel='settings_updated')

    # Aktualisiere Lobby
    broadcastPublicGames()


@socketio.on('start_game')
def handle_start_game():
    success, username, game = get_current_data(need_game=True)
    if not success:
        return

    # Nur Owner kann Spiel starten
    if game.owner != username:
        emit('error', {'message': 'Nur der Ersteller kann das Spiel starten'})
        return

    success, message = game.start_game()
    if not success:
        emit('error', {'message': message})
        return

    socketio.emit('info', {'message': 'Spiel gestartet'}, room=game.game_id)
    game.send_socket_game_update_for_all(channel='game_started')
    broadcastPublicGames()


# ########################################
#       Spielablauf
# ########################################

@socketio.on('submit_answers')
def handle_submit_answers(data):
    """Spieler gibt Antworten ab"""
    success, username, game = get_current_data(need_game=True)
    if not success:
        return

    success, error = game.submit_white_cards(username, as_dict(data).get('answer_indices'))
    if not success:
        emit('error', {'message': error})
        # Client zeigt ggf. schon "Warten" an -> korrekten Zustand schicken
        emit('game_state_update', game.get_socket_game_data(current_playerName=username))
        return

    socketio.emit('player_submitted', {
        'username': username,
        'submitted_count': len(game.submitted_white_cards),
        'total_players': len(game._non_czar_players())
    }, room=game.game_id)

    game.send_socket_game_update_for_all(channel='game_state_update')


@socketio.on('vote_winner')
def handle_vote_winner(data):
    """Card Czar wählt Gewinner"""
    success, username, game = get_current_data(need_game=True)
    if not success:
        return

    winner_index = as_dict(data).get('winner_index')
    if isinstance(winner_index, bool) or not isinstance(winner_index, int):
        emit('error', {'message': 'Ungültiger Index'})
        return

    if winner_index < 0 or winner_index >= len(game.player_mapping):
        emit('error', {'message': 'Index außerhalb des gültigen Bereichs'})
        return

    success, error = game.choose_winner(game.player_mapping[winner_index], username)
    if not success:
        emit('error', {'message': error})
        return

    game.send_socket_game_update_for_all(channel='game_state_update')


@socketio.on('submit_reaction')
def handle_submit_reaction(data):
    success, username, game = get_current_data(need_game=True)
    if not success:
        return
    data = as_dict(data)

    to_player_index = data.get('to_player_index', -1)
    points = data.get('points', 0)

    try:
        points = int(points)
        to_player_index = int(to_player_index)
    except (TypeError, ValueError):
        emit('error', {'message': 'Falscher Input'})
        return

    success, message = game.submit_reaction(username, to_player_index, points)
    if not success:
        emit('error', {'message': message})
        return

    emit('game_state_update', game.get_socket_game_data(current_playerName=username))


@socketio.on('submit_discard_cards')
def handle_submit_discard_cards(data):
    success, username, game = get_current_data(need_game=True)
    if not success:
        return

    success, message = game.submit_discard_cards(username, as_dict(data).get('card_ids'))
    if not success:
        emit('error', {'message': message})
        return

    emit('cards_discarded', {
        'username': username,
        'game': game.get_socket_game_data(current_playerName=username)
    })


@socketio.on('pause_game')
def handle_pause_game():
    success, username, game = get_current_data(need_game=True)
    if not success:
        return

    # Nur Owner kann pausieren
    if game.owner != username:
        emit('error', {'message': 'Nur der Ersteller kann das Spiel pausieren'})
        return

    success, message = game.pause()
    if not success:
        emit('error', {'message': message})
        return

    socketio.emit('game_paused', {
        'time_left': game.currentTimerSeconds,
        'max_time': game.currentTimerTotalSeconds
    }, room=game.game_id)


@socketio.on('resume_game')
def handle_resume_game():
    success, username, game = get_current_data(need_game=True)
    if not success:
        return

    # Nur Owner kann fortsetzen
    if game.owner != username:
        emit('error', {'message': 'Nur der Ersteller kann das Spiel fortsetzen'})
        return

    success, message, state_changed = game.resume()
    if not success:
        emit('error', {'message': message})
        return

    # Timer läuft automatisch weiter durch universal_timer_task
    socketio.emit('game_resumed', {
        'time_left': game.currentTimerSeconds,
        'max_time': game.currentTimerTotalSeconds
    }, room=game.game_id)
    if state_changed:
        game.send_socket_game_update_for_all()


@socketio.on('return_to_lobby')
def handle_return_to_lobby():
    success, username, game = get_current_data(need_game=True)
    if not success:
        return

    success, message = game.user_return_to_lobby(username)
    if not success:
        emit('error', {'message': message})
        return

    # Informiere alle Spieler
    game.send_socket_game_update_for_all(channel='game_state_update')
    broadcastPublicGames()


@socketio.on('reset_to_lobby')
def handle_reset_to_lobby():
    success, username, game = get_current_data(need_game=True)
    if not success:
        return

    # Nur Owner kann zurück zur Lobby
    if game.owner != username:
        emit('error', {'message': 'Nur der Ersteller kann das Spiel zurücksetzen'})
        return

    game.reset_to_lobby()

    game.send_socket_game_update_for_all(channel='game_reset_to_lobby')
    broadcastPublicGames()


if __name__ == '__main__':
    print(f"Starte Server... (debug={DEBUG})", flush=True)
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=DEBUG, use_reloader=DEBUG)
