const socket = io();
// Mache socket global verfügbar für andere Module
window.socket = socket;

// Initialisiere global ui object nach Socket-Initialisierung
window.ui = {};

// Initialisiere Game Settings nach Socket-Initialisierung
window.gameSettings.initialize();

// DOM Elements
const notification = document.getElementById('notification');

// Check for join link in URL
const urlParams = new URLSearchParams(window.location.search);
var joinGameId = urlParams.get('join');

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

// Versuche Reconnect beim Laden
window.addEventListener('load', () => {
    const savedUsername = window.ui.getSavedUsername();
    if (savedUsername) {
        socket.emit('reconnect_user', { username: savedUsername });
    }
});


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
    const pongTime = Date.now();
    const pingId = data.startTime;
    const latency = pongTime - pingId;
    pingDisplay.textContent = `${latency} ms`;
    // Hier könntest du die Latenz irgendwo im UI anzeigen, wenn gewünscht
});


// Handle Server-Neustart: Seite neu laden
socket.on('disconnect', () => {
    console.log('Verbindung zum Server verloren');
});

socket.on('connect', () => {
    console.log('Verbindung zum Server hergestellt');
    
    // Wenn wir bereits einen Username hatten und in einem Spiel waren,
    // aber der Server neugestartet wurde, laden wir die Seite neu
    if (window.currentUsername) {
        // Versuche zu reconnecten
        socket.emit('reconnect_user', { username: window.currentUsername });
    
    }
});

socket.on('reconnected', (data) => {

    if(data.reload) {
        clearSavedUsername();
        showNotification(data.message, 'error');
        //setTimeout(() => location.reload(), 1000);
        window.ui.showLoginScreen();
        return;
    }

    if(data.success) {
        if (data.game) {
            window.ui.showGameScreen(data.game);
        } else {
            window.ui.showServerLobby();
        }
    } else if(data.message) {
        showNotification(data.message, 'error');
        
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

// Utility
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
