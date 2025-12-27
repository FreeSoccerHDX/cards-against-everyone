# Cards Against Everyone

**Cards Against Everyone** ist ein webbasiertes Multiplayer-Partyspiel, inspiriert von "Cards Against Humanity". Die Anwendung nutzt Flask, Flask-SocketIO und Docker und ermöglicht es mehreren Spielern, gemeinsam in Echtzeit zu spielen.

---

## Inhaltsverzeichnis

- [Features](#features)
- [Lobby- & Spieleinstellungen](#lobby--spieleinstellungen)
- [Installation](#installation)
  - [Mit Docker (empfohlen)](#mit-docker-empfohlen)
  - [Ohne Docker](#ohne-docker)
- [Spielanleitung](#spielanleitung)
- [Technologien](#technologien)
- [Projektstruktur](#projektstruktur)
- [Entwicklung & Betrieb](#entwicklung--betrieb)
- [Lizenz](#lizenz)

---

## Features

- **Eindeutige Nutzernamen** mit automatischer Wiederverbindung (30s Timeout)
- **Lobby-System**: Öffentliche Spiele durchsuchen oder eigene erstellen
- **Flexible Spielerstellung**: Name, Sichtbarkeit, Passwortschutz
- **Live-Einstellungen**: Änderungen werden automatisch gespeichert
- **Join-Links**: Einfache Einladung per Link
- **Host-Migration**: Automatischer Host-Wechsel, falls der Ersteller das Spiel verlässt
- **Echtzeit-Kommunikation** über WebSockets

---

## Lobby- & Spieleinstellungen

Beim Erstellen oder Verwalten einer Lobby können folgende Einstellungen vorgenommen werden:

- **Spielname:** Individueller Name für das Spiel.
- **Sichtbarkeit:** Öffentlich (in der Lobby sichtbar) oder privat (nur per Link beitretbar).
- **Passwort:** Optionaler Passwortschutz für private Spiele.
- **Maximale Spieleranzahl:** Begrenzung der Teilnehmer (z.B. 3–10 Spieler).
- **Anzahl Handkarten:** Wie viele weiße Karten jeder Spieler auf der Hand hat.
- **Siegpunktzahl:** Anzahl der Punkte, die zum Gewinnen benötigt werden.
- **Zeitlimit pro Runde:** Maximale Zeit, um Karten auszuwählen (optional).
- **Kartensätze:** Auswahl, welche Kartendecks (z.B. Standard, Erweiterungen) verwendet werden.
- **Host-Wechsel:** Automatische Übertragung der Host-Rolle, falls der aktuelle Host das Spiel verlässt.

Alle Einstellungen können (sofern Host) auch während des Spiels angepasst werden, sofern dies nicht den Spielablauf stört.

---

## Installation

### Mit Docker (empfohlen)

1. Repository klonen:
    ```bash
    git clone https://github.com/dein-benutzername/cards-against-everyone.git
    cd cards-against-everyone
    ```
2. Container bauen und starten:
    ```bash
    docker-compose up --build
    ```
3. Anwendung im Browser öffnen: [http://localhost:5000](http://localhost:5000)

**Im Hintergrund starten:**
```bash
docker-compose up -d --build
```

### Ohne Docker

1. Abhängigkeiten installieren:
    ```bash
    pip install -r requirements.txt
    ```
2. Server starten:
    ```bash
    python app.py
    ```
3. Anwendung im Browser öffnen: [http://localhost:5000](http://localhost:5000)

---

## Spielanleitung

1. **Nutzername wählen:** Beim ersten Besuch festlegen.
2. **Lobby:** Öffentliche Spiele durchsuchen oder ein neues Spiel erstellen.
3. **Spiel erstellen:** Name, Sichtbarkeit und optional Passwort festlegen.
4. **Einstellungen:** Kartenanzahl, Siegpunkte etc. (nur Host).
5. **Freunde einladen:** Über Join-Link oder Lobby.
6. **Spiel starten:** Nur der Host, mindestens 3 Spieler erforderlich.
7. **Spielablauf:** Schwarze Karte lesen, weiße Karten auswählen, Host wählt die beste Antwort.

---

## Technologien

- **Backend:** Python, Flask, Flask-SocketIO
- **Frontend:** HTML, CSS, Vanilla JavaScript, Socket.IO Client
- **Containerisierung:** Docker, Docker Compose
- **Echtzeit:** WebSockets

---

## Projektstruktur

```
cards-against-everyone/
├── app.py                 # Flask-Backend mit Socket.IO
├── requirements.txt       # Python-Abhängigkeiten
├── Dockerfile             # Container-Definition
├── docker-compose.yml     # Docker Compose Konfiguration
├── templates/
│   └── index.html         # Haupt-HTML-Template
└── static/
    ├── style.css          # CSS-Styles
    └── script.js          # Frontend-Logik
```

---

## Entwicklung & Betrieb

- **Logs anzeigen:**  
  ```bash
  docker-compose logs -f
  ```
- **Container stoppen:**  
  ```bash
  docker-compose down
  ```
- **Hot-Reload im Development-Modus** (automatisch aktiviert)

---

## Lizenz

MIT License – siehe [LICENSE](LICENSE) für Details.
