const gameScreen = document.getElementById('game-screen');
window.currentGameData = null;

function showGameScreen(game) {
    window.ui.showScreen(gameScreen);
}


// Game Room created
socket.on('game_created', (game) => {
    console.log(game)
    window.currentGameData = game;
    currentGameId = game.id;
    currentGameCreator = game.creator;
    setIsCreator(true); 
    updateGameRoom(game);
    window.ui.showGameScreen(game);
    showNotification('Spiel erstellt!', 'success');
});

// Game Room joined
socket.on('game_joined', (data) => {
    currentGameId = data.game_id;
    currentGameCreator = data.game.creator;
    setIsCreator(data.game.creator === window.currentUsername);
    const isSpectator = data.is_spectator || false;
    
    // Speichere Player-Status
    if (data.player_statuses) {
        playerStatuses = data.player_statuses;
    }
    
    window.ui.showScreen(gameScreen);
    clearUrlParams(); // Entferne Join-Parameter aus URL
    
    // Wenn Spiel NICHT läuft - normale Lobby
    if (!data.game_started) {
        updateGameRoom(data.game);
        showNotification('Spiel beigetreten!', 'success');
        return;
    }
    
    // Spiel läuft bereits - initialisiere Spielzustand
    gameTitle.textContent = data.game.name;
    updatePlayersList(data.game.players, data.game.creator);
    if (data.spectator_statuses) {
        updateSpectatorsList(data.game.spectators || [], data.spectator_statuses);
    }
    
    // Zeige Spielbereich
    settingsPanel.style.display = 'none';
    gamePlayPanel.style.display = 'block';
    gameScreen.classList.add('playing');
    
    // Blende Spielerlisten aus
    const playersSection = document.querySelector('.players-panel');
    const spectatorsSection = document.getElementById('spectators-section');
    if (playersSection) playersSection.style.display = 'none';
    if (spectatorsSection) spectatorsSection.style.display = 'none';
    
    // Update game controls visibility
    if (window.isCreator) {
        pauseGameBtn.style.display = data.paused ? 'none' : 'inline-block';
        resumeGameBtn.style.display = data.paused ? 'inline-block' : 'none';
        resetLobbyBtn.style.display = 'inline-block';
    } else {
        pauseGameBtn.style.display = 'none';
        resumeGameBtn.style.display = 'none';
        resetLobbyBtn.style.display = 'none';
    }
    
    // Pause-Status
    if (data.paused) {
        isPaused = true;
        pauseOverlay.classList.add('active');
    } else {
        isPaused = false;
        pauseOverlay.classList.remove('active');
    }
    
    // Setze Czar-Info
    if (data.czar) {
        isCzar = data.is_czar;
        if (isSpectator) {
            czarText.textContent = `Card Czar: ${data.czar} (Du bist Zuschauer)`;
        } else {
            czarText.textContent = data.is_czar ? 
                'Du bist der Card Czar dieser Runde!' : 
                `Card Czar: ${data.czar}`;
        }
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
        
        if (cardsNeeded) {
            cardsNeeded.textContent = data.question.num_blanks;
        }
        if (selectionMax) {
            selectionMax.textContent = data.question.num_blanks;
        }
    }
    
    // Zeige Runden-Info
    if (data.win_score && winScoreLabel) {
        const maxRounds = data.max_rounds || 50;
        const currentRound = data.current_round || 1;
        winScoreLabel.textContent = `Spiel bis ${data.win_score} Punkte oder Runde ${currentRound}/${maxRounds}`;
        winScoreLabel.style.display = 'block';
    }
    
    // Zeige Hand-Karten nur für Spieler (nicht Spectators)
    if (data.hand && !isSpectator) {
        currentHand = data.hand;
        displayHand();
    } else {
        selectedCards = [];
        playerHand.innerHTML = '';
    }
    
    // Phase-spezifischer Zustand
    hideAllPhases();
    timerDisplay.style.display = 'block';
    
    if (data.round_phase === 'answering') {
        if (isSpectator) {
            czarWaitingPhase.style.display = 'block';
            czarWaitingTitle.textContent = 'Zuschauermodus';
            czarWaitingMessage.textContent = 'Du beobachtest das Spiel. Die Spieler wählen ihre Karten aus...';
        } else if (data.is_czar) {
            czarWaitingPhase.style.display = 'block';
            czarWaitingTitle.textContent = 'Du bist der Card Czar!';
            czarWaitingMessage.textContent = 'Warte, während die anderen Spieler ihre Karten auswählen...';
            if (data.submitted_count !== undefined && data.total_players !== undefined) {
                submissionStatus.textContent = `${data.submitted_count}/${data.total_players} Spieler haben abgegeben`;
            }
        } else if (data.has_submitted) {
            waitingVotePhase.style.display = 'block';
        } else {
            answerPhase.style.display = 'block';
            submitAnswersBtn.disabled = false;
        }
    } else if (data.round_phase === 'voting') {
        if (isSpectator) {
            waitingVotePhase.style.display = 'block';
            if (data.answer_options) {
                displayAnswerOptions(data.answer_options, false);
            }
        } else if (data.is_czar) {
            votingPhase.style.display = 'block';
            if (data.answer_options) {
                displayAnswerOptions(data.answer_options, true);
            }
        } else {
            waitingVotePhase.style.display = 'block';
            if (data.answer_options) {
                displayAnswerOptions(data.answer_options, false);
            }
        }
    } else if (data.round_phase === 'result') {
        resultPhase.style.display = 'block';
    }
    
    const message = isSpectator ? 
        'Als Zuschauer beigetreten!' : 
        'Spiel beigetreten! Du spielst ab der nächsten Runde mit.';
    showNotification(message, 'success');
});



function updateGameRoom(game, spectatorStatuses = {}) {
    gameTitle.textContent = game.name;
    
    // Speichere Creator
    currentGameCreator = game.creator;
    
    // Update players
    updatePlayersList(game.players, game.creator);
    
    // Update spectators
    updateSpectatorsList(game.spectators || [], spectatorStatuses);
    
    // Update join link
    const joinUrl = `${window.location.origin}?join=${game.id}`;
    joinLinkInput.value = joinUrl;
    
    // Update settings
    setIsCreator(game.creator === window.currentUsername);
    
    // Lade Settings über game-settings.js
    if (window.gameSettings) {
        window.gameSettings.load(game);
        window.gameSettings.updateAccess(window.isCreator);
    }
    
    // Show game or settings
    if (game.started) {
        console.log('updateGameRoom: game.started = true, hiding player lists');
        settingsPanel.style.display = 'none';
        gamePlayPanel.style.display = 'block';
        
        // Blende Spielerlisten aus während des Spiels
        const playersSection = document.querySelector('.players-panel');
        const spectatorsSection = document.getElementById('spectators-section');
        if (playersSection) playersSection.style.display = 'none';
        if (spectatorsSection) spectatorsSection.style.display = 'none';
        
        // Update game controls visibility
        if (window.isCreator) {
            pauseGameBtn.style.display = 'inline-block';
            resumeGameBtn.style.display = 'none';
            resetLobbyBtn.style.display = 'inline-block';
        } else {
            pauseGameBtn.style.display = 'none';
            resumeGameBtn.style.display = 'none';
            resetLobbyBtn.style.display = 'none';
        }
    } else {
        console.log('updateGameRoom: game.started = false, showing player lists');
        settingsPanel.style.display = 'block';
        gamePlayPanel.style.display = 'none';
        
        // Zeige Spielerlisten in der Lobby
        const playersSection = document.querySelector('.players-panel');
        const spectatorsSection = document.getElementById('spectators-section');
        if (playersSection) {
            playersSection.style.display = 'block';
            console.log('Set playersSection to block, current display:', playersSection.style.display);
        } else {
            console.log('ERROR: playersSection not found!');
        }
        if (spectatorsSection) {
            spectatorsSection.style.display = 'block';
            console.log('Set spectatorsSection to block, current display:', spectatorsSection.style.display);
        } else {
            console.log('ERROR: spectatorsSection not found!');
        }
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
        if (player === window.currentUsername) {
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
        
        // Kick-Button für Creator (nur wenn nicht selbst, nicht Creator und nicht gestartet)
        let kickButton = '';
        if (window.isCreator && player !== window.currentUsername && player !== currentGameCreator && currentGameCreator === window.currentUsername) {
            kickButton = `<button class="btn-kick" onclick="kickPlayer('${escapeHtml(player).replace(/'/g, "\\'")}')">Kick</button>`;
        }
        
        // Force-Role Button für Creator bei anderen Spielern (nur in Lobby)
        let forceRoleButton = '';
        if (window.isCreator && player !== window.currentUsername && settingsPanel.style.display !== 'none') {
            forceRoleButton = `<button class="btn-force-role" onclick="forceRole('${escapeHtml(player).replace(/'/g, "\\'")}')\" title="Zu Zuschauer verschieben">👁️</button>`;
        }
        
        // Toggle zu Spectator für eigenen Spieler (nicht während Spiel läuft)
        let toggleButton = '';
        if (player === window.currentUsername && settingsPanel.style.display !== 'none') {
            toggleButton = `<button class="btn-toggle-role" onclick="toggleRole()" title="Zu Zuschauer wechseln">👁️</button>`;
        }
        
        item.innerHTML = `
            <span>${statusIcon} ${escapeHtml(player)}${player === window.currentUsername ? ' (Du)' : ''}</span>
            <span class="player-actions">
                ${creator && player === creator ? '<span class="crown">👑</span>' : ''}
                ${toggleButton}
                ${forceRoleButton}
                ${kickButton}
            </span>
        `;
        
        // Wende Spielerfarbe an
        applyPlayerColor(item, player);
        
        playersListDiv.appendChild(item);
    });
}

function updateSpectatorsList(spectators, spectatorStatuses = {}) {
    const spectatorsSection = document.getElementById('spectators-section');
    const spectatorsListDiv = document.getElementById('spectators-list');
    
    if (!spectators || spectators.length === 0) {
        spectatorsSection.style.display = 'none';
        return;
    }
    
    spectatorsSection.style.display = 'block';
    spectatorsListDiv.innerHTML = '';
    
    spectators.forEach(spectator => {
        const item = document.createElement('div');
        item.className = 'player-item spectator-item';
        if (spectator === window.currentUsername) {
            item.classList.add('current-player');
        }
        
        // Status-Indikator
        const status = spectatorStatuses[spectator] || 'connected';
        let statusIcon = '';
        if (status === 'disconnecting') {
            statusIcon = '<span class="status-indicator disconnecting" title="Verbindung unterbrochen...">⏳</span>';
        } else if (status === 'connected') {
            statusIcon = '<span class="status-indicator connected" title="Verbunden">●</span>';
        }
        
        // Kick-Button für Creator (nicht für sich selbst oder den Creator)
        let kickButton = '';
        if (window.isCreator && spectator !== window.currentUsername && spectator !== currentGameCreator) {
            kickButton = `<button class="btn-kick" onclick="kickPlayer('${escapeHtml(spectator).replace(/'/g, "\\'")}')">Kick</button>`;
        }
        
        // Force-Role Button für Creator bei anderen Spectators (nur in Lobby)
        let forceRoleButton = '';
        if (window.isCreator && spectator !== window.currentUsername && settingsPanel.style.display !== 'none') {
            forceRoleButton = `<button class="btn-force-role" onclick="forceRole('${escapeHtml(spectator).replace(/'/g, "\\'")}')\" title="Zu Spieler verschieben">🎮</button>`;
        }
        
        // Toggle zu Spieler für eigenen Spectator (nicht während Spiel läuft)
        let toggleButton = '';
        if (spectator === window.currentUsername && settingsPanel.style.display !== 'none') {
            toggleButton = `<button class="btn-toggle-role" onclick="toggleRole()" title="Zu Spieler wechseln">🎮</button>`;
        }
        
        item.innerHTML = `
            <span>${statusIcon} ${escapeHtml(spectator)}${spectator === window.currentUsername ? ' (Du)' : ''} <span style="opacity: 0.6; font-size: 11px;">👁️</span></span>
            <span class="player-actions">
                ${toggleButton}
                ${forceRoleButton}
                ${kickButton}
            </span>
        `;
        
        // Wende Spielerfarbe an
        applyPlayerColor(item, spectator);
        
        spectatorsListDiv.appendChild(item);
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

// Toggle zwischen Spieler und Spectator
function toggleRole() {
    socket.emit('toggle_role');
}

// Force Role Change (nur für Creator)
function forceRole(username) {
    socket.emit('force_role', { username: username });
}

socket.on('role_changed', (data) => {
    // Update Listen
    updatePlayersList(data.players, currentGameCreator);
    updateSpectatorsList(data.spectators, {});
    
    // Notification
    if (data.username === window.currentUsername) {
        const role = data.is_spectator ? 'Zuschauer' : 'Spieler';
        if (data.forced_by) {
            showNotification(`${data.forced_by} hat dich zu ${role} verschoben`, 'info');
        } else {
            showNotification(`Du bist jetzt ${role}`, 'success');
        }
    } else {
        const role = data.is_spectator ? 'Zuschauer' : 'Spieler';
        showNotification(`${data.username} ist jetzt ${role}`, 'info');
    }
});

// Start Game Button Handler (in game-settings.js)

socket.on('game_started', (data) => {
    // Update Creator info
    currentGameCreator = data.game.creator;
    setIsCreator(data.game.creator === window.currentUsername);
    
    settingsPanel.style.display = 'none';
    gamePlayPanel.style.display = 'block';
    gameScreen.classList.add('playing');
    showNotification('Spiel gestartet!', 'success');
    
    // Blende Spielerlisten aus während des Spiels
    const playersSection = document.querySelector('.players-panel');
    const spectatorsSection = document.getElementById('spectators-section');
    if (playersSection) playersSection.style.display = 'none';
    if (spectatorsSection) spectatorsSection.style.display = 'none';
    
    // Show game controls for creator
    if (window.isCreator) {
        pauseGameBtn.style.display = 'inline-block';
        resumeGameBtn.style.display = 'none';
        resetLobbyBtn.style.display = 'inline-block';
    } else {
        pauseGameBtn.style.display = 'none';
        resumeGameBtn.style.display = 'none';
        resetLobbyBtn.style.display = 'none';
    }
});

socket.on('left_game', () => {
    currentGameId = null;
    currentGameCreator = null;
    setIsCreator(false);
    window.ui.showServerLobby();
});

window.ui.showGameScreen = showGameScreen;