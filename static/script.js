const socket = io();

let currentUsername = null;
let currentGameId = null;
let currentGameCreator = null; // Track den aktuellen Creator
let isCreator = false;
let selectedGameForJoin = null;

// DOM Elements
const usernameScreen = document.getElementById('username-screen');
const lobbyScreen = document.getElementById('lobby-screen');
const gameScreen = document.getElementById('game-screen');

const usernameInput = document.getElementById('username-input');
const usernameSubmit = document.getElementById('username-submit');
const usernameError = document.getElementById('username-error');

const currentUsernameDisplay = document.getElementById('current-username');
const createGameBtn = document.getElementById('create-game-btn');
const refreshGamesBtn = document.getElementById('refresh-games-btn');
const publicGamesDiv = document.getElementById('public-games');

const createGameModal = document.getElementById('create-game-modal');
const gameNameInput = document.getElementById('game-name-input');
const gamePublicCheckbox = document.getElementById('game-public-checkbox');
const gamePasswordInput = document.getElementById('game-password-input');
const createGameConfirm = document.getElementById('create-game-confirm');
const createGameCancel = document.getElementById('create-game-cancel');

const joinGameModal = document.getElementById('join-game-modal');
const joinGameName = document.getElementById('join-game-name');
const joinPasswordGroup = document.getElementById('join-password-group');
const joinPasswordInput = document.getElementById('join-password-input');
const joinGameConfirm = document.getElementById('join-game-confirm');
const joinGameCancel = document.getElementById('join-game-cancel');

const gameTitle = document.getElementById('game-title');
const leaveGameBtn = document.getElementById('leave-game-btn');
const playersListDiv = document.getElementById('players-list');
const joinLinkInput = document.getElementById('join-link');
const copyLinkBtn = document.getElementById('copy-link-btn');

const settingsName = document.getElementById('settings-name');
const settingsPublic = document.getElementById('settings-public');
const settingsPassword = document.getElementById('settings-password');
const settingsMaxCards = document.getElementById('settings-max-cards');
const settingsWinScore = document.getElementById('settings-win-score');
const creatorInfo = document.getElementById('creator-info');
const startGameBtn = document.getElementById('start-game-btn');

const settingsPanel = document.getElementById('settings-panel');
const gamePlayPanel = document.getElementById('game-play-panel');

const notification = document.getElementById('notification');

// Check for join link in URL
const urlParams = new URLSearchParams(window.location.search);
const joinGameId = urlParams.get('join');
let pendingJoinGameId = null; // Für Passwort-Abfrage

// Utility Functions
function showScreen(screen) {
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
    screen.classList.add('active');
}

function clearUrlParams() {
    // Entferne URL-Parameter nach erfolgreichem Join
    const url = new URL(window.location);
    url.search = '';
    window.history.replaceState({}, '', url);
}

function showNotification(message, type = 'info') {
    notification.textContent = message;
    notification.className = 'notification show';
    if (type === 'error') notification.classList.add('error');
    if (type === 'success') notification.classList.add('success');
    
    setTimeout(() => {
        notification.classList.remove('show');
    }, 3000);
}

function showModal(modal) {
    modal.classList.add('active');
}

function hideModal(modal) {
    modal.classList.remove('active');
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

// Username Screen
usernameSubmit.addEventListener('click', submitUsername);
usernameInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') submitUsername();
});

function submitUsername() {
    const username = usernameInput.value.trim();
    if (!username) {
        usernameError.textContent = 'Bitte gib einen Namen ein';
        return;
    }
    
    socket.emit('set_username', { username });
}

// Versuche Reconnect beim Laden
window.addEventListener('load', () => {
    const savedUsername = getSavedUsername();
    if (savedUsername) {
        socket.emit('reconnect_user', { username: savedUsername });
    }
});

// Socket Events
socket.on('username_set', (data) => {
    currentUsername = data.username;
    saveUsername(currentUsername);
    currentUsernameDisplay.textContent = currentUsername;
    usernameError.textContent = '';
    
    // Prüfe ob Join-Link vorhanden ist
    if (joinGameId) {
        // Hole erst Spielinformationen
        socket.emit('get_game_info', { game_id: joinGameId });
    } else {
        showScreen(lobbyScreen);
        socket.emit('get_public_games');
    }
});

socket.on('username_error', (data) => {
    usernameError.textContent = data.message;
    showNotification(data.message, 'error');
});

socket.on('reconnected', (data) => {
    currentUsername = data.username;
    currentUsernameDisplay.textContent = currentUsername;
    
    if (data.game_id && data.game) {
        currentGameId = data.game_id;
        updateGameRoom(data.game);
        showScreen(gameScreen);
    } else if (joinGameId) {
        // Wenn Join-Link vorhanden, hole Spielinfo
        socket.emit('get_game_info', { game_id: joinGameId });
    } else {
        showScreen(lobbyScreen);
        socket.emit('get_public_games');
    }
});

// Lobby
createGameBtn.addEventListener('click', () => {
    gameNameInput.value = `${currentUsername}'s Spiel`;
    gamePublicCheckbox.checked = true;
    gamePasswordInput.value = '';
    showModal(createGameModal);
});

refreshGamesBtn.addEventListener('click', () => {
    socket.emit('get_public_games');
});

createGameConfirm.addEventListener('click', () => {
    const name = gameNameInput.value.trim() || 'Neues Spiel';
    const isPublic = gamePublicCheckbox.checked;
    const password = gamePasswordInput.value.trim();
    
    socket.emit('create_game', {
        name,
        is_public: isPublic,
        password
    });
    
    hideModal(createGameModal);
});

createGameCancel.addEventListener('click', () => {
    hideModal(createGameModal);
});

socket.on('public_games', (data) => {
    displayPublicGames(data.games);
});

socket.on('lobby_update', (data) => {
    displayPublicGames(data.games);
});

function displayPublicGames(games) {
    if (!games || games.length === 0) {
        publicGamesDiv.innerHTML = '<p class="empty-message">Keine öffentlichen Spiele verfügbar</p>';
        return;
    }
    
    publicGamesDiv.innerHTML = '';
    games.forEach(game => {
        const card = document.createElement('div');
        card.className = 'game-card';
        card.innerHTML = `
            <h3>${escapeHtml(game.name)}</h3>
            <div class="game-info">
                <span>👥 ${game.players} Spieler</span>
                ${game.has_password ? '<span class="lock-icon">🔒</span>' : ''}
            </div>
        `;
        card.addEventListener('click', () => {
            selectedGameForJoin = game;
            joinGameName.textContent = `Beitritt zu: ${game.name}`;
            if (game.has_password) {
                joinPasswordGroup.style.display = 'block';
                joinPasswordInput.value = '';
            } else {
                joinPasswordGroup.style.display = 'none';
            }
            showModal(joinGameModal);
        });
        publicGamesDiv.appendChild(card);
    });
}

joinGameConfirm.addEventListener('click', () => {
    const password = joinPasswordInput.value.trim();
    
    // Prüfe ob es ein Join-Link oder Lobby-Join ist
    if (pendingJoinGameId) {
        socket.emit('join_game', {
            game_id: pendingJoinGameId,
            password
        });
        pendingJoinGameId = null;
    } else if (selectedGameForJoin) {
        socket.emit('join_game', {
            game_id: selectedGameForJoin.id,
            password
        });
    }
    
    hideModal(joinGameModal);
});

joinGameCancel.addEventListener('click', () => {
    hideModal(joinGameModal);
    selectedGameForJoin = null;
    pendingJoinGameId = null;
});

// Handle game info response (für Join-Links)
socket.on('game_info', (data) => {
    if (data.started) {
        showNotification('Spiel bereits gestartet', 'error');
        showScreen(lobbyScreen);
        socket.emit('get_public_games');
        clearUrlParams();
        return;
    }
    
    if (data.has_password) {
        // Zeige Passwort-Modal
        pendingJoinGameId = data.game_id;
        joinGameName.textContent = `Beitritt zu: ${data.name}`;
        joinPasswordGroup.style.display = 'block';
        joinPasswordInput.value = '';
        showScreen(lobbyScreen); // Zeige Lobby im Hintergrund
        showModal(joinGameModal);
    } else {
        // Kein Passwort, direkt beitreten
        socket.emit('join_game', { game_id: data.game_id });
    }
});

socket.on('game_info_error', (data) => {
    showNotification(data.message, 'error');
    showScreen(lobbyScreen);
    socket.emit('get_public_games');
    clearUrlParams();
});

// Game Room
socket.on('game_created', (data) => {
    currentGameId = data.game_id;
    currentGameCreator = data.game.creator;
    isCreator = true;
    updateGameRoom(data.game);
    showScreen(gameScreen);
    showNotification('Spiel erstellt!', 'success');
});

socket.on('game_joined', (data) => {
    currentGameId = data.game_id;
    currentGameCreator = data.game.creator;
    isCreator = (data.game.creator === currentUsername);
    updateGameRoom(data.game);
    showScreen(gameScreen);
    showNotification('Spiel beigetreten!', 'success');
    clearUrlParams(); // Entferne Join-Parameter aus URL
});

socket.on('player_joined', (data) => {
    showNotification(`${data.username} ist beigetreten`, 'info');
    updatePlayersList(data.players, currentGameCreator);
});

socket.on('player_left', (data) => {
    showNotification(`${data.username} hat das Spiel verlassen`, 'info');
    currentGameCreator = data.creator; // Aktualisiere Creator (könnte sich geändert haben)
    updatePlayersList(data.players, data.creator);
});

socket.on('settings_updated', (data) => {
    currentGameCreator = data.game.creator; // Könnte sich theoretisch ändern
    updateGameRoom(data.game);
});

leaveGameBtn.addEventListener('click', () => {
    if (confirm('Möchtest du wirklich zur Lobby zurückkehren?')) {
        socket.emit('leave_game');
    }
});

socket.on('left_game', () => {
    currentGameId = null;
    currentGameCreator = null;
    isCreator = false;
    showScreen(lobbyScreen);
    socket.emit('get_public_games');
});

function updateGameRoom(game) {
    gameTitle.textContent = game.name;
    
    // Speichere Creator
    currentGameCreator = game.creator;
    
    // Update players
    updatePlayersList(game.players, game.creator);
    
    // Update join link
    const joinUrl = `${window.location.origin}?join=${game.id}`;
    joinLinkInput.value = joinUrl;
    
    // Update settings
    isCreator = (game.creator === currentUsername);
    
    settingsName.value = game.name;
    settingsPublic.checked = game.is_public;
    settingsPassword.value = game.password || '';
    settingsMaxCards.value = game.settings.max_cards;
    settingsWinScore.value = game.settings.win_score;
    
    // Disable settings for non-creators
    const settingsInputs = document.querySelectorAll('.settings-input');
    settingsInputs.forEach(input => {
        input.disabled = !isCreator;
    });
    
    if (isCreator) {
        creatorInfo.style.display = 'none';
        startGameBtn.style.display = 'block';
    } else {
        creatorInfo.style.display = 'block';
        startGameBtn.style.display = 'none';
    }
    
    // Show game or settings
    if (game.started) {
        settingsPanel.style.display = 'none';
        gamePlayPanel.style.display = 'block';
    } else {
        settingsPanel.style.display = 'block';
        gamePlayPanel.style.display = 'none';
    }
}

function updatePlayersList(players, creator) {
    playersListDiv.innerHTML = '';
    players.forEach(player => {
        const item = document.createElement('div');
        item.className = 'player-item';
        if (creator && player === creator) {
            item.classList.add('creator');
        }
        if (player === currentUsername) {
            item.classList.add('current-player');
        }
        item.innerHTML = `
            <span>${escapeHtml(player)}${player === currentUsername ? ' (Du)' : ''}</span>
            ${creator && player === creator ? '<span class="crown">👑</span>' : ''}
        `;
        playersListDiv.appendChild(item);
    });
}

copyLinkBtn.addEventListener('click', () => {
    joinLinkInput.select();
    navigator.clipboard.writeText(joinLinkInput.value);
    showNotification('Link kopiert!', 'success');
});

// Settings auto-save
let settingsTimeout = null;

function autoSaveSettings() {
    if (!isCreator) return;
    
    clearTimeout(settingsTimeout);
    settingsTimeout = setTimeout(() => {
        const data = {
            name: settingsName.value.trim(),
            is_public: settingsPublic.checked,
            password: settingsPassword.value.trim(),
            settings: {
                max_cards: parseInt(settingsMaxCards.value),
                win_score: parseInt(settingsWinScore.value)
            }
        };
        socket.emit('update_settings', data);
    }, 500);
}

settingsName.addEventListener('input', autoSaveSettings);
settingsPublic.addEventListener('change', autoSaveSettings);
settingsPassword.addEventListener('input', autoSaveSettings);
settingsMaxCards.addEventListener('input', autoSaveSettings);
settingsWinScore.addEventListener('input', autoSaveSettings);

// Start Game
startGameBtn.addEventListener('click', () => {
    socket.emit('start_game');
});

socket.on('game_started', (data) => {
    settingsPanel.style.display = 'none';
    gamePlayPanel.style.display = 'block';
    showNotification('Spiel gestartet!', 'success');
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
