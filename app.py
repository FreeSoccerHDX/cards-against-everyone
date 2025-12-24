from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import uuid
import time
from threading import Timer

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
        # Starte 30-Sekunden-Timer
        if username in disconnect_timers:
            disconnect_timers[username].cancel()
        
        timer = Timer(30.0, cleanup_user, args=[username])
        disconnect_timers[username] = timer
        timer.start()

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
        disconnect_timers[username].cancel()
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
            disconnect_timers[username].cancel()
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
            'max_cards': 10,
            'win_score': 7
        },
        'started': False
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
    
    # Informiere alle Spieler
    emit('game_started', {'game': game}, room=game_id)
    
    # Aktualisiere Lobby
    socketio.emit('lobby_update', {'games': get_public_games()})

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
