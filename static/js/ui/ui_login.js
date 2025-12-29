const loginScreen = document.getElementById('login-screen');

const usernameInput = document.getElementById('username-input');
const usernameSubmit = document.getElementById('username-submit');
const usernameError = document.getElementById('username-error');

// Globale Variablen
window.currentUsername = null;

getRandomFunnyName();

function showLoginScreen() {
    window.ui.showScreen(loginScreen);
}

function resetAllData() {
    usernameInput.value = '';
    usernameError.textContent = '';
}

// LocalStorage für Reconnect
function saveUsername(username) {
    localStorage.setItem('cae_username', username);
}
function getSavedUsername() {
    return localStorage.getItem('cae_username');
}
function clearSavedUsername() {
    localStorage.removeItem('cae_username');
}


// Socket Events
socket.on('username_set', (data) => {
    console.log("Username set:", data, data.username);
    window.currentUsername = data.username;
    saveUsername(window.currentUsername);
    currentUsernameDisplay.textContent = window.currentUsername;
    usernameError.textContent = '';

    if(!data.hasGame) {   
        // Prüfe ob Join-Link vorhanden ist
        if (joinGameId) {
            // Hole erst Spielinformationen
            socket.emit('get_game_info_link_join', { game_id: joinGameId });
            joinGameId = null; // Nur einmal versuchen
            clearUrlParams();
        } else {
            window.ui.showServerLobby();
        }
    }
});

socket.on('username_error', (data) => {
    usernameError.textContent = data.message;
    showNotification(data.message, 'error');
    
    // Wenn wir bereits im Spiel waren aber Session abgelaufen ist (Server-Neustart),
    // lösche gespeicherte Daten und lade neu
    if (data.message.includes('abgelaufen')) {
        clearSavedUsername();
        setTimeout(() => location.reload(), 1000);
    }
});

// Username Screen
usernameSubmit.addEventListener('click', submitUsername);
usernameInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') submitUsername();
});

function submitUsername() {
    let username = usernameInput.value.trim();
    
    if (!username) {
        usernameError.textContent = 'Bitte gib einen Namen ein';
        return;
    }
    
    // Ersetze mehrfache Leerzeichen durch ein einzelnes
    username = username.replace(/\s+/g, ' ');
    
    // Prüfe Länge (min 2, max 20 Zeichen)
    if (username.length < 2) {
        usernameError.textContent = 'Der Name muss mindestens 2 Zeichen lang sein';
        return;
    }
    
    if (username.length > 30) {
        usernameError.textContent = 'Der Name darf maximal 30 Zeichen lang sein (aktuell: ' + username.length + ')';
        return;
    }
    
    // Update input field mit bereinigtem Namen
    usernameInput.value = username;
    
    socket.emit('set_username', { username });
}

window.ui.showLoginScreen = showLoginScreen;
window.ui.resetAllData = resetAllData;
window.ui.saveUsername = saveUsername;
window.ui.getSavedUsername = getSavedUsername;
window.ui.clearSavedUsername = clearSavedUsername;