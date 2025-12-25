const socket = io();

let currentUsername = null;
let currentGameId = null;
let currentGameCreator = null; // Track den aktuellen Creator
let isCreator = false;
let isPaused = false; // Track Pause-Status
let selectedGameForJoin = null;
let playerStatuses = {}; // Track player connection statuses

// DOM Elements
const usernameScreen = document.getElementById('username-screen');
const lobbyScreen = document.getElementById('lobby-screen');
const gameScreen = document.getElementById('game-screen');

const usernameInput = document.getElementById('username-input');
const usernameSubmit = document.getElementById('username-submit');
const usernameError = document.getElementById('username-error');

const currentUsernameDisplay = document.getElementById('current-username');
const logoutBtn = document.getElementById('logout-btn');
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
const settingsMaxRounds = document.getElementById('settings-max-rounds');
const settingsAnswerTime = document.getElementById('settings-answer-time');
const settingsCzarTime = document.getElementById('settings-czar-time');
const settingsRoundDelay = document.getElementById('settings-round-delay');
const creatorInfo = document.getElementById('creator-info');
const startGameBtn = document.getElementById('start-game-btn');

const settingsPanel = document.getElementById('settings-panel');
const gamePlayPanel = document.getElementById('game-play-panel');

const pauseGameBtn = document.getElementById('pause-game-btn');
const resumeGameBtn = document.getElementById('resume-game-btn');
const resetLobbyBtn = document.getElementById('reset-lobby-btn');
const pauseOverlay = document.getElementById('pause-overlay');

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
    
    if (username.length > 20) {
        usernameError.textContent = 'Der Name darf maximal 20 Zeichen lang sein';
        return;
    }
    
    // Update input field mit bereinigtem Namen
    usernameInput.value = username;
    
    socket.emit('set_username', { username });
}

// Versuche Reconnect beim Laden
window.addEventListener('load', () => {
    const savedUsername = getSavedUsername();
    if (savedUsername) {
        socket.emit('reconnect_user', { username: savedUsername });
    }
});

// Handle Server-Neustart: Seite neu laden
socket.on('disconnect', () => {
    console.log('Verbindung zum Server verloren');
});

socket.on('connect', () => {
    console.log('Verbindung zum Server hergestellt');
    
    // Wenn wir bereits einen Username hatten und in einem Spiel waren,
    // aber der Server neugestartet wurde, laden wir die Seite neu
    if (currentUsername && currentGameId) {
        // Versuche zu reconnecten
        socket.emit('reconnect_user', { username: currentUsername });
        
        // Wenn nach kurzer Zeit keine Antwort kommt, neu laden
        setTimeout(() => {
            // Prüfe ob wir noch im Spiel sind
            if (currentGameId) {
                console.log('Server-Neustart erkannt, lade Seite neu...');
                clearSavedUsername();
                location.reload();
            }
        }, 1000);
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
    
    // Wenn wir bereits im Spiel waren aber Session abgelaufen ist (Server-Neustart),
    // lösche gespeicherte Daten und lade neu
    if (data.message.includes('abgelaufen') && currentGameId) {
        clearSavedUsername();
        setTimeout(() => location.reload(), 1000);
    }
});

socket.on('reconnected', (data) => {
    currentUsername = data.username;
    currentUsernameDisplay.textContent = currentUsername;
    
    if (data.game_id && data.game) {
        currentGameId = data.game_id;
        
        // Initialize player statuses
        if (data.player_statuses) {
            playerStatuses = data.player_statuses;
        }
        
        // Wenn Spiel läuft, stelle Spielzustand wieder her
        if (data.game_started && data.round_phase) {
            // Update grundlegende Game-Infos
            currentGameCreator = data.game.creator;
            isCreator = (data.game.creator === currentUsername);
            gameTitle.textContent = data.game.name;
            updatePlayersList(data.game.players, data.game.creator);
            
            // Zeige Spielbereich
            showScreen(gameScreen);
            settingsPanel.style.display = 'none';
            gamePlayPanel.style.display = 'block';
            gameScreen.classList.add('playing');
            
            // Update game controls visibility
            if (isCreator) {
                pauseGameBtn.style.display = 'inline-block';
                resumeGameBtn.style.display = 'none';
                resetLobbyBtn.style.display = 'inline-block';
            } else {
                pauseGameBtn.style.display = 'none';
                resumeGameBtn.style.display = 'none';
                resetLobbyBtn.style.display = 'none';
            }
            
            // Pause-Status wiederherstellen
            if (data.paused) {
                isPaused = true;
                pauseOverlay.classList.add('active');
                if (isCreator) {
                    pauseGameBtn.style.display = 'none';
                    resumeGameBtn.style.display = 'inline-block';
                }
            } else {
                isPaused = false;
                pauseOverlay.classList.remove('active');
            }
            
            // Setze Czar-Text
            if (data.czar) {
                isCzar = data.is_czar; // Setze globalen isCzar Status
                czarText.textContent = data.is_czar ? 
                    'Du bist der Card Czar dieser Runde!' : 
                    `Card Czar: ${data.czar}`;
            }
            
            // Setze Scores
            if (data.scores) {
                updateScores(data.scores);
            }
            
            // Setze Timer
            if (data.timer !== undefined) {
                updateTimerDisplay(data.timer, data.answer_time || data.czar_time || 60);
            }
            
            // Zeige Frage wenn vorhanden
            if (data.question) {
                currentQuestion = data.question;
                questionText.innerHTML = data.question.card_text.replace(/_____/g, '<span class="blank">_____</span>');
                
                // Setze Anzahl benötigter Karten
                if (cardsNeeded) {
                    cardsNeeded.textContent = data.question.num_blanks;
                }
                if (selectionMax) {
                    selectionMax.textContent = data.question.num_blanks;
                }
            }
            
            // Zeige Hand-Karten nur wenn noch nicht abgegeben
            if (data.hand && !data.has_submitted) {
                currentHand = data.hand;
                displayHand();
            } else if (data.has_submitted) {
                // Hand ausblenden wenn bereits abgegeben
                selectedCards = [];
                playerHand.innerHTML = '';
            }
            
            // Phase-spezifischer Zustand
            if (data.round_phase === 'answering') {
                answerPhase.style.display = 'none';
                votingPhase.style.display = 'none';
                resultPhase.style.display = 'none';
                czarWaitingPhase.style.display = 'none';
                waitingVotePhase.style.display = 'none';
                
                if (data.is_czar) {
                    czarWaitingPhase.style.display = 'block';
                } else if (data.has_submitted) {
                    // Bereits abgegeben - zeige Warte-Phase
                    waitingVotePhase.style.display = 'block';
                } else {
                    // Noch nicht abgegeben - zeige Antwort-Phase
                    answerPhase.style.display = 'block';
                    submitAnswersBtn.disabled = false;
                }
                
                // Zeige Submission Count
                if (data.submitted_count !== undefined && data.total_players !== undefined) {
                    submissionStatus.textContent = `${data.submitted_count}/${data.total_players} Spieler haben abgegeben`;
                }
                
            } else if (data.round_phase === 'voting') {
                answerPhase.style.display = 'none';
                votingPhase.style.display = 'none';
                resultPhase.style.display = 'none';
                czarWaitingPhase.style.display = 'none';
                waitingVotePhase.style.display = 'none';
                
                if (data.is_czar) {
                    votingPhase.style.display = 'block';
                    // Zeige Voting-Optionen für Czar (interaktiv)
                    if (data.answer_options) {
                        displayAnswerOptions(data.answer_options, true);
                    }
                } else {
                    waitingVotePhase.style.display = 'block';
                    // Zeige Voting-Optionen für Nicht-Czar (read-only)
                    if (data.answer_options) {
                        displayAnswerOptions(data.answer_options, false);
                    }
                }
                
            } else if (data.round_phase === 'result') {
                answerPhase.style.display = 'none';
                votingPhase.style.display = 'none';
                czarWaitingPhase.style.display = 'none';
                waitingVotePhase.style.display = 'none';
                resultPhase.style.display = 'block';
            }
            
        } else {
            // Spiel nicht gestartet, zeige normale Lobby
            updateGameRoom(data.game);
            showScreen(gameScreen);
        }
    } else if (joinGameId) {
        // Wenn Join-Link vorhanden, hole Spielinfo
        socket.emit('get_game_info', { game_id: joinGameId });
    } else {
        showScreen(lobbyScreen);
        socket.emit('get_public_games');
    }
});

// Logout
logoutBtn.addEventListener('click', async () => {
    if (await customConfirm('Möchtest du dich wirklich abmelden?', 'Abmelden')) {
        // Lösche gespeicherten Username
        clearSavedUsername();
        
        // Verlasse ggf. Spiel
        if (currentGameId) {
            socket.emit('leave_game');
        }
        
        // Reset Zustand
        currentUsername = null;
        currentGameId = null;
        currentGameCreator = null;
        isCreator = false;
        
        // Gehe zu Username-Screen
        showScreen(usernameScreen);
        usernameInput.value = '';
        usernameError.textContent = '';
        
        showNotification('Abgemeldet', 'info');
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
    if (data.has_password) {
        // Zeige Passwort-Modal
        pendingJoinGameId = data.game_id;
        joinGameName.textContent = `Beitritt zu: ${data.name}${data.started ? ' (läuft bereits)' : ''}`;
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
    
    // Speichere Player-Status
    if (data.player_statuses) {
        playerStatuses = data.player_statuses;
    }
    
    updateGameRoom(data.game);
    showScreen(gameScreen);
    
    if (data.game.started) {
        showNotification('Spiel beigetreten! Du spielst ab der nächsten Runde mit.', 'success');
    } else {
        showNotification('Spiel beigetreten!', 'success');
    }
    
    clearUrlParams(); // Entferne Join-Parameter aus URL
});

socket.on('player_joined', (data) => {
    // Set new player as connected
    playerStatuses[data.username] = 'connected';
    showNotification(`${data.username} ist beigetreten`, 'info');
    updatePlayersList(data.players, currentGameCreator);
});

socket.on('player_status_changed', (data) => {
    // Update player status
    playerStatuses[data.username] = data.status;
    // Refresh players list using current DOM state
    const players = Array.from(document.querySelectorAll('.player-item')).map(item => {
        const text = item.querySelector('span:first-child').textContent;
        return text.replace(' (Du)', '').replace(/[●⏳]\s*/, '').trim();
    });
    updatePlayersList(players, currentGameCreator);
});

socket.on('kicked_from_game', (data) => {
    showNotification(data.message, 'error');
    currentGameId = null;
    currentGameCreator = null;
    isCreator = false;
    playerStatuses = {};
    showScreen(lobbyScreen);
    socket.emit('get_public_games');
});

socket.on('player_left', (data) => {
    // Remove player from statuses
    delete playerStatuses[data.username];
    showNotification(`${data.username} hat das Spiel verlassen`, 'info');
    currentGameCreator = data.creator; // Aktualisiere Creator (könnte sich geändert haben)
    updatePlayersList(data.players, data.creator);
});

socket.on('settings_updated', (data) => {
    currentGameCreator = data.game.creator; // Könnte sich theoretisch ändern
    updateGameRoom(data.game);
});

pauseGameBtn.addEventListener('click', () => {
    socket.emit('pause_game');
});

resumeGameBtn.addEventListener('click', () => {
    socket.emit('resume_game');
});

resetLobbyBtn.addEventListener('click', async () => {
    if (await customConfirm('Alle Spielfortschritte werden gelöscht und das Spiel wird in die Lobby zurückgesetzt.', 'Spiel zurücksetzen?')) {
        socket.emit('reset_to_lobby');
    }
});

leaveGameBtn.addEventListener('click', async () => {
    if (await customConfirm('Möchtest du wirklich zur Lobby zurückkehren?', 'Spiel verlassen')) {
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
    settingsAnswerTime.value = game.settings.answer_time || 60;
    settingsCzarTime.value = game.settings.czar_time || 30;
    settingsRoundDelay.value = game.settings.round_delay || 5;
    
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
        
        // Update game controls visibility
        if (isCreator) {
            pauseGameBtn.style.display = 'inline-block';
            resumeGameBtn.style.display = 'none';
            resetLobbyBtn.style.display = 'inline-block';
        } else {
            pauseGameBtn.style.display = 'none';
            resumeGameBtn.style.display = 'none';
            resetLobbyBtn.style.display = 'none';
        }
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
        
        // Status-Indikator
        const status = playerStatuses[player] || 'connected';
        let statusIcon = '';
        if (status === 'disconnecting') {
            statusIcon = '<span class="status-indicator disconnecting" title="Verbindung unterbrochen...">⏳</span>';
        } else if (status === 'connected') {
            statusIcon = '<span class="status-indicator connected" title="Verbunden">●</span>';
        }
        
        // Kick-Button für Creator (nur wenn nicht selbst und nicht gestartet)
        let kickButton = '';
        if (isCreator && player !== currentUsername && currentGameCreator === currentUsername) {
            kickButton = `<button class="btn-kick" onclick="kickPlayer('${escapeHtml(player).replace(/'/g, "\\'")}')">Kick</button>`;
        }
        
        item.innerHTML = `
            <span>${statusIcon} ${escapeHtml(player)}${player === currentUsername ? ' (Du)' : ''}</span>
            <span class="player-actions">
                ${creator && player === creator ? '<span class="crown">👑</span>' : ''}
                ${kickButton}
            </span>
        `;
        
        // Wende Spielerfarbe an
        applyPlayerColor(item, player);
        
        playersListDiv.appendChild(item);
    });
}

copyLinkBtn.addEventListener('click', () => {
    joinLinkInput.select();
    navigator.clipboard.writeText(joinLinkInput.value);
    showNotification('Link kopiert!', 'success');
});

// Kick Player Function
async function kickPlayer(username) {
    if (await customConfirm(`${username} wird aus dem Spiel entfernt und kann nicht mehr zurückkehren.`, `Spieler ${username} entfernen?`)) {
        socket.emit('kick_player', { username: username });
    }
}

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
                win_score: parseInt(settingsWinScore.value),
                max_rounds: parseInt(settingsMaxRounds.value),
                answer_time: parseInt(settingsAnswerTime.value),
                czar_time: parseInt(settingsCzarTime.value),
                round_delay: parseInt(settingsRoundDelay.value)
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
settingsMaxRounds.addEventListener('input', autoSaveSettings);
settingsAnswerTime.addEventListener('input', autoSaveSettings);
settingsCzarTime.addEventListener('input', autoSaveSettings);
settingsRoundDelay.addEventListener('input', autoSaveSettings);

// Start Game
startGameBtn.addEventListener('click', () => {
    socket.emit('start_game');
});

socket.on('game_started', (data) => {
    settingsPanel.style.display = 'none';
    gamePlayPanel.style.display = 'block';
    gameScreen.classList.add('playing');
    showNotification('Spiel gestartet!', 'success');
    
    // Show game controls for creator
    if (isCreator) {
        pauseGameBtn.style.display = 'inline-block';
        resumeGameBtn.style.display = 'none';
        resetLobbyBtn.style.display = 'inline-block';
    } else {
        pauseGameBtn.style.display = 'none';
        resumeGameBtn.style.display = 'none';
        resetLobbyBtn.style.display = 'none';
    }
});

// Game Play Variables
let currentHand = [];
let selectedCards = [];
let currentQuestion = null;
let isCzar = false;

// Game Play Elements
const czarInfo = document.getElementById('czar-info');
const czarText = document.getElementById('czar-text');
const questionText = document.getElementById('question-text');
const timerDisplay = document.getElementById('timer-display');
const scoresPanel = document.getElementById('scores-panel');
const winScoreLabel = document.getElementById('win-score-label');

const answerPhase = document.getElementById('answer-phase');
const cardsNeeded = document.getElementById('cards-needed');
const selectionCount = document.getElementById('selection-count');
const selectionMax = document.getElementById('selection-max');
const playerHand = document.getElementById('player-hand');
const submitAnswersBtn = document.getElementById('submit-answers-btn');

const czarWaitingPhase = document.getElementById('czar-waiting-phase');
const submissionStatus = document.getElementById('submission-status');

const votingPhase = document.getElementById('voting-phase');
const answerOptions = document.getElementById('answer-options');

const waitingVotePhase = document.getElementById('waiting-vote-phase');
const resultPhase = document.getElementById('result-phase');
const roundWinner = document.getElementById('round-winner');

const gameEndPhase = document.getElementById('game-end-phase');
const gameWinner = document.getElementById('game-winner');
const finalScores = document.getElementById('final-scores');
const backToLobbyBtn = document.getElementById('back-to-lobby-btn');

// Round Started
socket.on('round_started', (data) => {
    currentQuestion = data.question;
    currentHand = data.hand;
    isCzar = data.is_czar;
    selectedCards = [];
    
    // Zeige Czar Info und Question Card wieder (falls nach game_ended ausgeblendet)
    czarInfo.style.display = 'block';
    document.querySelector('.question-card').style.display = 'block';
    scoresPanel.style.display = 'flex';
    
    // Update UI
    czarText.textContent = data.is_czar ? 
        'Du bist der Card Czar dieser Runde!' : 
        `Card Czar: ${data.czar}`;
    
    // Ersetze nur komplette Blanks (5 Unterstriche)
    questionText.innerHTML = data.question.card_text.replace(/_____/g, '<span class="blank">_____</span>');
    
    updateScores(data.scores);
    
    // Zeige Ziel-Punktzahl und Runden-Info
    if (data.win_score && winScoreLabel) {
        const maxRounds = data.max_rounds || 50;
        const currentRound = data.current_round || 1;
        winScoreLabel.textContent = `Spiel bis ${data.win_score} Punkte oder Runde ${currentRound}/${maxRounds}`;
        winScoreLabel.style.display = 'block';
    }
    
    // Hide all phases ZUERST
    hideAllPhases();
    
    // Timer anzeigen und initial setzen
    timerDisplay.style.display = 'block';
    if (data.answer_time) {
        updateTimerDisplay(data.answer_time, data.answer_time);
    }
    
    if (isCzar) {
        // Card Czar wartet - Timer sichtbar
        czarWaitingPhase.style.display = 'block';
        submissionStatus.textContent = '0 von ' + (Object.keys(data.scores).length - 1) + ' Spielern haben abgegeben';
    } else {
        // Spieler wählt Karten - Timer sichtbar
        answerPhase.style.display = 'block';
        cardsNeeded.textContent = data.question.num_blanks;
        selectionMax.textContent = data.question.num_blanks;
        displayHand();
    }
});

let maxTimerValue = 60; // Wird beim Start der Runde gesetzt

function updateTimerDisplay(timeLeft, maxTime) {
    // Setze maxTime wenn vorhanden
    if (maxTime !== undefined) {
        maxTimerValue = maxTime;
    }
    
    // Timer ausblenden bei -1
    if (timeLeft < 0) {
        timerDisplay.style.display = 'none';
        return;
    }
    
    timerDisplay.style.display = 'block';
    
    const timerSeconds = document.getElementById('timer-seconds');
    const timerCircle = document.querySelector('.timer-circle-progress');
    const timerText = document.querySelector('.timer-text');
    
    // Update Zahl
    timerSeconds.textContent = timeLeft;
    
    // Berechne Prozentsatz für Kreis (r=22 für kleineren Kreis)
    const circumference = 2 * Math.PI * 22;
    const progress = timeLeft / maxTimerValue;
    const offset = circumference * (1 - progress);
    
    timerCircle.style.strokeDashoffset = offset;
    
    // Farbe basierend auf verbleibender Zeit
    timerCircle.classList.remove('warning', 'danger');
    timerText.classList.remove('danger');
    
    const percentLeft = (timeLeft / maxTimerValue) * 100;
    
    if (percentLeft <= 20 || timeLeft <= 10) {
        // Rot: Weniger als 20% oder 10 Sekunden
        timerCircle.classList.add('danger');
        timerText.classList.add('danger');
    } else if (percentLeft <= 50 || timeLeft <= 20) {
        // Gelb: Weniger als 50% oder 20 Sekunden
        timerCircle.classList.add('warning');
    }
    // Sonst grün (Standard)
}

// Timer-Sync vom Server (jede Sekunde)
socket.on('timer_sync', (data) => {
    // Aktualisiere Display direkt mit Server-Zeit
    if (data.time_left !== undefined) {
        updateTimerDisplay(data.time_left, data.max_time);
    }
});



function hideAllPhases() {
    // Stop countdowns
    if (nextRoundCountdown) {
        clearInterval(nextRoundCountdown);
        nextRoundCountdown = null;
    }
    
    answerPhase.style.display = 'none';
    czarWaitingPhase.style.display = 'none';
    votingPhase.style.display = 'none';
    waitingVotePhase.style.display = 'none';
    
    // Leere alte Voting-Optionen
    answerOptions.innerHTML = '';
    const waitingAnswerOptions = document.getElementById('waiting-answer-options');
    if (waitingAnswerOptions) {
        waitingAnswerOptions.innerHTML = '';
    }
    resultPhase.style.display = 'none';
    gameEndPhase.style.display = 'none';
}

function updateScores(scores) {
    scoresPanel.innerHTML = '';
    const maxScore = Math.max(...Object.values(scores));
    
    for (const [player, score] of Object.entries(scores)) {
        const item = document.createElement('div');
        item.className = 'score-item';
        if (score === maxScore && score > 0) {
            item.classList.add('leading');
        }
        item.innerHTML = `
            <span class="score-name">${escapeHtml(player)}</span>
            <span class="score-value">${score}</span>
        `;
        
        // Wende Spielerfarbe an
        applyPlayerColor(item, player);
        
        scoresPanel.appendChild(item);
    }
}

function displayHand() {
    playerHand.innerHTML = '';
    currentHand.forEach((card, index) => {
        const cardEl = document.createElement('div');
        cardEl.className = 'answer-card';
        cardEl.textContent = card;
        cardEl.dataset.index = index;
        
        cardEl.addEventListener('click', () => toggleCardSelection(index, cardEl));
        
        playerHand.appendChild(cardEl);
    });
    
    updateSelectionUI();
}

function toggleCardSelection(index, cardEl) {
    // Blockiere während Pause
    if (isPaused) {
        return;
    }
    
    const selectedIndex = selectedCards.indexOf(index);
    
    if (selectedIndex > -1) {
        // Deselect
        selectedCards.splice(selectedIndex, 1);
        cardEl.classList.remove('selected');
        cardEl.querySelector('.selection-number')?.remove();
    } else {
        // Select
        if (selectedCards.length < currentQuestion.num_blanks) {
            selectedCards.push(index);
            cardEl.classList.add('selected');
            
            const numberBadge = document.createElement('div');
            numberBadge.className = 'selection-number';
            numberBadge.textContent = selectedCards.length;
            cardEl.appendChild(numberBadge);
        }
    }
    
    updateSelectionUI();
}

function updateSelectionUI() {
    selectionCount.textContent = selectedCards.length;
    const isComplete = selectedCards.length === currentQuestion.num_blanks;
    submitAnswersBtn.disabled = !isComplete;
    
    // Update button text with count and icon
    const icon = isComplete ? '✓' : '✗';
    submitAnswersBtn.textContent = `${icon} Abgabe (${selectedCards.length}/${currentQuestion.num_blanks})`;
    
    // Update button class based on completion
    if (isComplete) {
        submitAnswersBtn.classList.add('submit-complete');
        submitAnswersBtn.classList.remove('submit-incomplete');
    } else {
        submitAnswersBtn.classList.add('submit-incomplete');
        submitAnswersBtn.classList.remove('submit-complete');
    }
    
    // Update numbers on selected cards
    document.querySelectorAll('.answer-card.selected').forEach(card => {
        const index = parseInt(card.dataset.index);
        const position = selectedCards.indexOf(index) + 1;
        const badge = card.querySelector('.selection-number');
        if (badge) {
            badge.textContent = position;
        }
    });
}

submitAnswersBtn.addEventListener('click', () => {
    socket.emit('submit_answers', { answer_indices: selectedCards });
    answerPhase.style.display = 'none';
    waitingVotePhase.style.display = 'block';
});

// Player submitted
socket.on('player_submitted', (data) => {
    if (isCzar) {
        submissionStatus.textContent = `${data.submitted_count} von ${data.total_players} Spielern haben abgegeben`;
    }
    showNotification(`${data.username} hat abgegeben`, 'info');
});

// Voting Phase
socket.on('voting_phase', (data) => {
    hideAllPhases();
    
    // Timer wird vom Server via timer_sync gesetzt
    timerDisplay.style.display = 'block';
    
    if (isCzar) {
        votingPhase.style.display = 'block';
        displayAnswerOptions(data.answer_options, true);
    } else {
        waitingVotePhase.style.display = 'block';
        // Zeige Antworten auch für Nicht-Czar Spieler (read-only)
        displayAnswerOptions(data.answer_options, false);
    }
});

function displayAnswerOptions(options, interactive = true) {
    const container = interactive ? answerOptions : document.getElementById('waiting-answer-options');
    container.innerHTML = '';
    
    options.forEach((option, index) => {
        const optionEl = document.createElement('div');
        optionEl.className = 'answer-option';
        if (!interactive) {
            optionEl.classList.add('readonly');
        }
        
        const answerText = currentQuestion.card_text;
        let filledText = answerText;
        
        option.answers.forEach((answer, i) => {
            filledText = filledText.replace('_____', `<strong>${escapeHtml(answer)}</strong>`);
        });
        
        optionEl.innerHTML = `<div class="answer-text">${filledText}</div>`;
        
        if (interactive) {
            optionEl.addEventListener('click', () => selectWinner(index, optionEl));
        }
        
        container.appendChild(optionEl);
    });
}

function selectWinner(index, optionEl) {
    // Blockiere während Pause
    if (isPaused) {
        return;
    }
    
    document.querySelectorAll('.answer-option').forEach(el => el.classList.remove('selected-winner'));
    optionEl.classList.add('selected-winner');
    
    // Stoppe Timer sofort wenn Czar auswählt
    
    socket.emit('vote_winner', { winner_index: index });
}

// Round Result
let nextRoundCountdown = null;

socket.on('round_result', (data) => {
    timerDisplay.style.display = 'none';
    hideAllPhases();
    resultPhase.style.display = 'block';
    
    // Zeige Frage mit eingesetzten Gewinnerantworten
    const resultQuestion = document.getElementById('result-question');
    const resultAnswers = document.getElementById('result-answers');
    
    if (resultQuestion && data.question && data.winner_answers) {
        let questionText = data.question.card_text;
        // Ersetze jedes "_____" durch die entsprechende Antwort
        data.winner_answers.forEach(answer => {
            questionText = questionText.replace('_____', `<strong class="filled-answer">${answer}</strong>`);
        });
        resultQuestion.innerHTML = questionText;
    }
    
    // Verstecke separaten Antworten-Bereich (Antworten sind jetzt in der Frage)
    if (resultAnswers) {
        resultAnswers.style.display = 'none';
    }
    
    // Handle disconnected winner
    if (data.winner === null && data.disconnected_player) {
        roundWinner.textContent = `${data.disconnected_player} (hat das Spiel verlassen)`;
        showNotification(`${data.disconnected_player} wurde gew\u00e4hlt, hat aber das Spiel verlassen - kein Punkt vergeben`, 'info');
    } else if (data.winner) {
        roundWinner.textContent = data.winner;
        showNotification(`${data.winner} gewinnt diese Runde!`, 'success');
    } else {
        roundWinner.textContent = 'Kein Gewinner';
    }
    
    updateScores(data.scores);
    
    // Starte Countdown
    const countdownEl = document.getElementById('countdown-timer');
    let timeLeft = data.next_round_in || 5;
    countdownEl.textContent = timeLeft;
    
    if (nextRoundCountdown) {
        clearInterval(nextRoundCountdown);
    }
    
    nextRoundCountdown = setInterval(() => {
        timeLeft--;
        countdownEl.textContent = timeLeft;
        
        if (timeLeft <= 0) {
            clearInterval(nextRoundCountdown);
        }
    }, 1000);
});

// Game Ended
socket.on('game_ended', (data) => {
    hideAllPhases();
    gameEndPhase.style.display = 'block';
    gameWinner.textContent = data.winner;
    
    // Blende Czar Info, Frage-Karte und Scores-Panel aus
    czarInfo.style.display = 'none';
    document.querySelector('.question-card').style.display = 'none';
    scoresPanel.style.display = 'none';
    
    // Zeige letzte Frage mit gewinnenden Antworten ausgefüllt
    if (data.last_question && data.winner_answers && data.winner_answers.length > 0) {
        const endQuestion = document.getElementById('end-question');
        if (endQuestion) {
            let questionText = data.last_question.card_text;
            // Ersetze Blanks durch gewinnende Antworten mit Styling
            data.winner_answers.forEach(answer => {
                questionText = questionText.replace('_____', `<span class="filled-answer">${escapeHtml(answer)}</span>`);
            });
            endQuestion.innerHTML = questionText;
        }
    } else if (data.last_question) {
        // Fallback: Zeige Frage ohne Antworten falls keine vorhanden
        const endQuestion = document.getElementById('end-question');
        if (endQuestion) {
            endQuestion.innerHTML = data.last_question.card_text.replace(/_____/g, '<span class="blank">_____</span>');
        }
    }
    
    
    // Zeige auch die aktuelle Scoreboard-Ansicht (nicht nur Endstand)
    if (data.final_scores) {
        updateScores(data.final_scores);
    }
    
    // Zeige Endstand sortiert
    finalScores.innerHTML = '';
    const sortedScores = Object.entries(data.final_scores).sort((a, b) => b[1] - a[1]);
    
    sortedScores.forEach(([player, score], index) => {
        const item = document.createElement('div');
        item.className = 'final-score-item';
        if (index === 0) item.classList.add('winner');
        item.innerHTML = `
            <span>${index + 1}. ${escapeHtml(player)}</span>
            <span>${score} Punkte</span>
        `;
        
        // Wende Spielerfarbe an
        applyPlayerColor(item, player);
        
        finalScores.appendChild(item);
    });
    
    // Zeige Round History
    displayRoundHistory(data.round_history || []);
});

function displayRoundHistory(history) {
    const container = document.getElementById('round-history-container');
    if (!container) return;
    
    container.innerHTML = '';
    
    if (history.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: #999;">Keine Runden gespielt</p>';
        return;
    }
    
    // Zeige Runden in umgekehrter Reihenfolge (neueste zuerst)
    history.slice().reverse().forEach((round) => {
        const card = document.createElement('div');
        card.className = 'history-card';
        
        // Fülle die Frage mit den gewinnenden Antworten
        let filledQuestion = round.question.card_text;
        round.winner_answers.forEach(answer => {
            filledQuestion = filledQuestion.replace('_____', `<span class="filled-answer">${escapeHtml(answer)}</span>`);
        });
        
        const czarColors = generatePlayerColor(round.czar);
        const winnerColors = generatePlayerColor(round.winner);
        
        card.innerHTML = `
            <div class="history-card-header">
                <span class="round-number">Runde ${round.round_num}</span>
            </div>
            <div class="history-question-filled">
                ${filledQuestion}
            </div>
            <div class="history-meta">
                <div class="history-meta-item">
                    <span>👑</span>
                    <span class="player-badge" style="background-color: ${czarColors.bgColor}; color: ${czarColors.textColor};"><strong>${escapeHtml(round.czar)}</strong></span>
                </div>
                <div class="history-meta-item">
                    <span>🏆</span>
                    <span class="player-badge" style="background-color: ${winnerColors.bgColor}; color: ${winnerColors.textColor};"><strong>${escapeHtml(round.winner)}</strong></span>
                </div>
            </div>
        `;
        
        container.appendChild(card);
    });
}

// Pause/Resume Events
socket.on('game_paused', (data) => {
    isPaused = true;
    pauseOverlay.style.display = 'flex';
    pauseGameBtn.style.display = 'none';
    resumeGameBtn.style.display = isCreator ? 'inline-block' : 'none';
    
    // Zeige verbleibende Zeit an
    if (data.time_left !== undefined) {
        updateTimerDisplay(data.time_left);
    }
    
    // Deaktiviere alle Interaktionen
    submitAnswersBtn.disabled = true;
    const cards = document.querySelectorAll('.card');
    cards.forEach(card => card.style.pointerEvents = 'none');
    const answerOptions = document.querySelectorAll('.answer-option');
    answerOptions.forEach(option => option.style.pointerEvents = 'none');
    
    showNotification('Spiel pausiert', 'info');
});

socket.on('game_resumed', (data) => {
    isPaused = false;
    pauseOverlay.style.display = 'none';
    pauseGameBtn.style.display = isCreator ? 'inline-block' : 'none';
    resumeGameBtn.style.display = 'none';
    
    // Aktiviere Interaktionen wieder
    submitAnswersBtn.disabled = selectedCards.length === 0;
    const cards = document.querySelectorAll('.card');
    cards.forEach(card => card.style.pointerEvents = 'auto');
    const answerOptions = document.querySelectorAll('.answer-option');
    answerOptions.forEach(option => option.style.pointerEvents = 'auto');
    
    showNotification('Spiel fortgesetzt', 'success');
});

socket.on('game_reset_to_lobby', (data) => {
    // Zurück zur Game-Lobby
    isPaused = false;
    settingsPanel.style.display = 'block';
    gamePlayPanel.style.display = 'none';
    pauseOverlay.style.display = 'none';
    
    // Zeige Czar Info, Question Card und Scores-Panel wieder
    czarInfo.style.display = 'block';
    document.querySelector('.question-card').style.display = 'block';
    scoresPanel.style.display = 'flex';
    
    updateGameRoom(data.game);
    showNotification('Spiel wurde zurückgesetzt', 'info');
});

backToLobbyBtn.addEventListener('click', () => {
    gameScreen.classList.remove('playing');
    settingsPanel.style.display = 'block';
    gamePlayPanel.style.display = 'none';
    hideAllPhases();
    
    // Zeige Czar Info, Question Card und Scores-Panel wieder
    czarInfo.style.display = 'block';
    document.querySelector('.question-card').style.display = 'block';
    scoresPanel.style.display = 'flex';
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
