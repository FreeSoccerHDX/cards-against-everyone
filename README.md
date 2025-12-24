# Cards Against Everyone

Ein multiplayer "Cards Against Humanity"-Spiel mit Flask, Socket.IO und Docker.

## Features

- **Nutzerverwaltung**: Eindeutige Nutzernamen, automatische Reconnect-Funktion (30s Timeout)
- **Lobby-System**: Öffentliche Spiele anzeigen oder eigene Spiele erstellen
- **Spielerstellung**: Name, Sichtbarkeit und Passwortschutz konfigurierbar
- **Live-Einstellungen**: Spieleinstellungen werden automatisch gespeichert
- **Join-Links**: Direkter Beitritt über teilbare Links
- **Host-Migration**: Wenn der Ersteller geht, wird der nächste Spieler zum Host

## Installation und Start

### Mit Docker (empfohlen)

```bash
# Container bauen und starten
docker-compose up --build

# Im Hintergrund ausführen
docker-compose up -d --build
```

Die Anwendung ist dann unter `http://localhost:5000` erreichbar.

### Ohne Docker

```bash
# Abhängigkeiten installieren
pip install -r requirements.txt

# Server starten
python app.py
```

## Technologie-Stack

- **Backend**: Flask + Flask-SocketIO
- **Frontend**: Vanilla JavaScript + Socket.IO Client
- **Container**: Docker + Docker Compose
- **Real-time**: WebSockets

## Spielablauf

1. **Nutzername festlegen** beim ersten Besuch
2. **Lobby**: Öffentliche Spiele anzeigen oder eigenes Spiel erstellen
3. **Spiel erstellen**: Name, Sichtbarkeit, Passwort konfigurieren
4. **Einstellungen**: Kartenanzahl, Siegpunkte, etc. (nur Host)
5. **Spieler einladen**: Via Join-Link oder Lobby
6. **Spiel starten**: Nur der Host kann das Spiel starten (mindestens 3 Spieler)

## Entwicklung

Die Anwendung läuft im Development-Modus mit Auto-Reload:

```bash
# Logs anzeigen
docker-compose logs -f

# Container stoppen
docker-compose down
```

## Struktur

```
cards-against-everyone/
├── app.py                 # Flask Backend mit Socket.IO
├── requirements.txt       # Python Dependencies
├── Dockerfile            # Container-Definition
├── docker-compose.yml    # Docker Compose Config
├── templates/
│   └── index.html        # HTML Template
└── static/
    ├── style.css         # Styling
    └── script.js         # Frontend-Logik
```

## Lizenz

MIT
