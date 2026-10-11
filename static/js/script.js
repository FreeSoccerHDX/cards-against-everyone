const socket = io();
// Mache socket global verfügbar für andere Module
window.socket = socket;

// Initialisiere global ui object nach Socket-Initialisierung
window.ui = {};

// Initialisiere Game Settings nach Socket-Initialisierung
window.gameSettings.initialize();

// DOM Elements
const notification = document.getElementById('notification');
const connectionBanner = document.getElementById('connection-banner');
const sessionTakenOverOverlay = document.getElementById('session-taken-over-overlay');
const sessionTakeBackBtn = document.getElementById('session-take-back-btn');

// Check for join link in URL
const urlParams = new URLSearchParams(window.location.search);
var joinGameId = urlParams.get('join');

// true, wenn ein anderer Tab die Sitzung übernommen hat -> nicht automatisch zurückholen
var sessionTakenOver = false;

function clearUrlParams() {
    // Entferne URL-Parameter nach erfolgreichem Join
    const url = new URL(window.location);
    url.search = '';
    window.history.replaceState({}, '', url);
}


var lastNotificationTimeout = null;
function showNotification(message, type = 'info') {
    notification.textContent = message;
    notification.className = 'notification show';
    if (type === 'error') notification.classList.add('error');
    if (type === 'success') notification.classList.add('success');
    if (type === 'warning') notification.classList.add('warning');

    if (lastNotificationTimeout) {
        clearTimeout(lastNotificationTimeout);
    }
    lastNotificationTimeout = setTimeout(() => {
        notification.classList.remove('show');
    }, 3000);
}


var currentPingID = 0;
// Ping Event
function sendPing() {
    socket.emit('ping', {
        "pingId": currentPingID++ ,
        "startTime": Date.now()
    });
}
sendPing(); // Sofortiger Ping beim Start
setInterval(() => {
    sendPing();
}, 5000);

const pingDisplay = document.getElementById('ping');
socket.on('pong', (data) => {
    const latency = Date.now() - data.startTime;
    pingDisplay.textContent = `${latency} ms`;
});


// Verbindung verloren: Banner anzeigen, Socket.IO verbindet automatisch neu
socket.on('disconnect', () => {
    console.log('Verbindung zum Server verloren');
    connectionBanner.classList.remove('hidden');
});

socket.on('connect', () => {
    console.log('Verbindung zum Server hergestellt');
    connectionBanner.classList.add('hidden');

    // Mit gespeichertem Token die Sitzung wiederherstellen (auch nach Seiten-Reload)
    const token = window.ui.getSavedToken();
    if (token && !sessionTakenOver) {
        socket.emit('reconnect_user', { token: token });
    }
});

// Tab wieder sichtbar (z.B. Handy entsperrt): sofort neu verbinden bzw. Zustand holen
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState !== 'visible' || sessionTakenOver) {
        return;
    }
    if (!socket.connected) {
        socket.connect();
    } else if (window.currentGameData) {
        socket.emit('get_game_state');
    }
});

socket.on('reconnected', (data) => {
    if (data.reload) {
        window.ui.clearSavedToken();
        window.currentUsername = null;
        window.currentGameData = null;
        showNotification(data.message, 'error');
        window.ui.showLoginScreen();
        return;
    }

    if (data.success && data.game) {
        window.ui.showGameScreen(data.game);
    }
    // Ohne Spiel zeigt 'username_set' die Server-Lobby an
});

// Anderer Tab hat die Sitzung übernommen
socket.on('session_taken_over', () => {
    sessionTakenOver = true;
    sessionTakenOverOverlay.classList.remove('hidden');
});

sessionTakeBackBtn.addEventListener('click', () => {
    sessionTakenOver = false;
    sessionTakenOverOverlay.classList.add('hidden');
    const token = window.ui.getSavedToken();
    if (!socket.connected) {
        socket.connect(); // 'connect' schickt reconnect_user
    } else if (token) {
        socket.emit('reconnect_user', { token: token });
    } else {
        window.ui.showLoginScreen();
    }
});

// Handle game info response (für Join-Links)
socket.on('game_info_link_join', (game) => {
    window.ui.showServerLobby(); // Zeige Lobby im Hintergrund
    window.ui.showJoinGameModal(game); // Zeige Join-Modal
});

// Handle game info error-response (für Join-Links)
socket.on('game_info_link_join_error', (data) => {
    showNotification(data.message, 'error');
    window.ui.showServerLobby();
    clearUrlParams();
});

// Error handling
socket.on('error', (data) => {
    showNotification(data.message, 'error');
});

socket.on('info', (data) => {
    showNotification(data.message, 'info');
});

socket.on('success', (data) => {
    showNotification(data.message, 'success');
});

// Utility
function escapeHtml(text) {
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}
