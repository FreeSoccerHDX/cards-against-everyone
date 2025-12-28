window.currentGameData = null;

// Game Play Variables
var currentHand = [];
var selectedCards = [];

// ########################################
//
//             Game Universal Elements
//
// ########################################
const gameScreen = document.getElementById('game-screen');
const gameLobbyContent = document.getElementById('game-lobby-content');
const gamePlayContent = document.getElementById('game-play-content');
const gameEndContent = document.getElementById('game-end-content');

const gameTitle = document.getElementById('game-title');
const leaveGameBtn = document.getElementById('leave-game-btn');
leaveGameBtn.addEventListener('click', async () => {
    if (await customConfirm('Möchtest du wirklich zur Lobby zurückkehren?', 'Spiel verlassen')) {
        socket.emit('leave_game');
    }
});

// ########################################
//
//             Game Lobby Elements
//
// ########################################
const playersList = document.getElementById('players-list');
const spectatorsSection = document.getElementById('spectators-section');
const spectatorsList = document.getElementById('spectators-list');
const joinLinkInput = document.getElementById('join-link');
const copyLinkBtn = document.getElementById('copy-link-btn');



// ########################################
//
//             Game Play Elements
//
// ########################################
const votingPhaseTitle = document.getElementById('voting-phase-title');
const waitingVotePhase = document.getElementById('waiting-vote-phase');
const gameControls = document.getElementById('game-controls');
const pauseGameBtn = document.getElementById('pause-game-btn');
const resumeGameBtn = document.getElementById('resume-game-btn');
const resetLobbyBtn = document.getElementById('reset-lobby-btn');

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

const pauseOverlay = document.getElementById('pause-overlay');

const czarInfo = document.getElementById('czar-info');
const czarText = document.getElementById('czar-text');

const questionText = document.getElementById('question-text');
const timerDisplay = document.getElementById('timer-display');
const timerSeconds = document.getElementById('timer-seconds');

const winScoreLabel = document.getElementById('win-score-label');
const scoresPanel = document.getElementById('scores-panel');

const answerPhase = document.getElementById('answer-phase');
const cardsNeeded = document.getElementById('cards-needed');
const selectionCount = document.getElementById('selection-count');
const selectionMax = document.getElementById('selection-max');
const playerHand = document.getElementById('player-hand');
const submitAnswersBtn = document.getElementById('submit-answers-btn');
submitAnswersBtn.addEventListener('click', () => {
    socket.emit('submit_answers', { answer_indices: selectedCards });
    answerPhase.classList.add('hidden');
    waitingVotePhase.classList.remove('hidden');
});

const czarWaitingPhase = document.getElementById('czar-waiting-phase');
const czarWaitingTitle = document.getElementById('czar-waiting-title');
const czarWaitingMessage = document.getElementById('czar-waiting-message');
const submissionStatus = document.getElementById('submission-status');

// Für aktuellen Czar für Voting -> alle anderen können nur zuschauen
const votingPhase = document.getElementById('voting-phase');
const answerOptionsList = document.getElementById('answer-options-list');

const resultPhase = document.getElementById('result-phase');
const roundWinner = document.getElementById('round-winner');
const resultQuestion = document.getElementById('result-question');
const resultAnswers = document.getElementById('result-answers');
const countdownTimer = document.getElementById('countdown-timer');

// ########################################
//
//             Game End Elements
//
// ########################################
const gameWinner = document.getElementById('game-winner');
const finalScores = document.getElementById('final-scores');
const roundHistorySection = document.getElementById('round-history-section');
const roundHistoryContainer = document.getElementById('round-history-container');

const backToLobbyBtn = document.getElementById('back-to-lobby-btn');
backToLobbyBtn.addEventListener('click', () => {
    window.currentGameData.state = 'lobby'; // setze zustand lokal zurück
    updateGameRoom(window.currentGameData);
});



function showGameScreen(game) {
    window.currentGameData = game;
    window.ui.showScreen(gameScreen);
    updateGameRoom(game);
}


socket.on('settings_updated', (game) => {
    currentGameCreator = game.creator;
    window.currentGameData = game;
    updateGameRoom(game);
});

socket.on('player_joined', (data) => {
    const message = data.is_spectator ? 
        `${data.username} ist als Zuschauer beigetreten` : 
        `${data.username} ist beigetreten`;
    showNotification(message, 'info');

    window.currentGameData.active_players = data.game.active_players
    window.currentGameData.spectators = data.game.spectators
    updateLobbyPlayerList(data.game);
});

socket.on('player_status_changed', (data) => {
    // Update Creator falls vorhanden (könnte sich durch Disconnects geändert haben)
    //console.error("unhandled player_status_changed:", data);
    window.currentGameData.player_status[data.username] = data.status;
    updateLobbyPlayerList(window.currentGameData);
    update_scores(window.currentGameData);
});

// Spieler kicked from the game
socket.on('kicked_from_game', (data) => {
    showNotification(data.message, 'error');
    window.currentGameData = null;
    window.ui.showServerLobby();
});


socket.on('player_left', (data) => {
    // Remove player from statuses
    showNotification(`${data.username} hat das Spiel verlassen`, 'info');
    let game = data.game;
    window.currentGameData = game;
    updateGameRoom(game);
});


// Pause/Resume Events
socket.on('game_paused', (data) => {
    window.currentGameData.paused = true;
    update_pauseOverlay(true);
    updateTimerDisplay(data.time_left);

    //pauseOverlay.style.display = 'flex';
    //pauseGameBtn.style.display = 'none';
    //resumeGameBtn.style.display = (window.currentGameData.owner == window.currentUsername) ? 'inline-block' : 'none';
});

socket.on('game_resumed', (data) => {
    window.currentGameData.paused = false;
    update_pauseOverlay(false);
    updateTimerDisplay(data.time_left);
    //pauseOverlay.style.display = 'none';
    //pauseGameBtn.style.display = (window.currentGameData.owner == window.currentUsername) ? 'inline-block' : 'none';
    //resumeGameBtn.style.display = 'none';
});

function update_pauseOverlay(paused) {
    if(pauseOverlay.classList.contains('hidden') && !paused) {
        return;
    }

    pauseOverlay.classList.toggle('hidden', !paused);
    pauseGameBtn.classList.toggle('hidden', paused || (window.currentGameData.owner != window.currentUsername));
    resumeGameBtn.classList.toggle('hidden', !paused || (window.currentGameData.owner != window.currentUsername));

    if(paused) {
        // Deaktiviere alle Interaktionen
        submitAnswersBtn.disabled = true;
        const cards = document.querySelectorAll('.card');
        cards.forEach(card => card.style.pointerEvents = 'none');
        const answerOptions = document.querySelectorAll('.answer-option');
        answerOptions.forEach(option => option.style.pointerEvents = 'none');
        
        showNotification('Spiel pausiert', 'info');
    } else {
        // Aktiviere Interaktionen wieder
        submitAnswersBtn.disabled = selectedCards.length === 0;
        const cards = document.querySelectorAll('.card');
        cards.forEach(card => card.style.pointerEvents = 'auto');
        const answerOptions = document.querySelectorAll('.answer-option');
        answerOptions.forEach(option => option.style.pointerEvents = 'auto');
        
        showNotification('Spiel fortgesetzt', 'success');
    }
}


// Aktualisiere Spielinformationen (z.B. nach Spielende wenn zurück zur Lobby)
socket.on('game_state_update', (game) => {
    window.currentGameData = game;
    updateGameRoom(game);
});

// Game Room created
socket.on('game_created', (game) => {
    //console.log(game);
    showGameScreen(game);
    showNotification('Spiel erstellt!', 'success');
});


function updateTimerDisplay(timeLeft, maxTime) {
    // Timer ausblenden bei -1
    timerDisplay.classList.add('hidden');
    countdownTimer.classList.add('hidden');

    if (timeLeft < 0) {
        return;
    }

    if(window.currentGameData.state == "countdown_next_round") {
        countdownTimer.classList.remove('hidden');
        countdownTimer.textContent = timeLeft;
        return;
    }
    timerDisplay.classList.remove('hidden');
    
    
    const timerSeconds = document.getElementById('timer-seconds');
    const timerCircle = document.querySelector('.timer-circle-progress');
    const timerText = document.querySelector('.timer-text');
    
    // Update Zahl
    timerSeconds.textContent = timeLeft;
    
    // Berechne Prozentsatz für Kreis (r=22 für kleineren Kreis)
    const circumference = 2 * Math.PI * 22;
    const progress = timeLeft / maxTime;
    const offset = circumference * (1 - progress);
    
    timerCircle.style.strokeDashoffset = offset;
    
    // Farbe basierend auf verbleibender Zeit
    timerCircle.classList.remove('warning', 'danger');
    timerText.classList.remove('danger');
    
    const percentLeft = (timeLeft / maxTime) * 100;
    
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

// Game Room joined
socket.on('game_joined', (game) => {
    //console.log("game_joined:", game);
    setInviteLinkVisibility(false);
    showGameScreen(game);
    showNotification('Spiel beigetreten!', 'success');
});

function toggleCardSelection(index, cardEl) {
    // Blockiere während Pause
    //console.log("toggleCardSelection", index);
    if (window.currentGameData.paused) {
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
        let currentQuestion = window.currentGameData.current_black_card;
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
    
    let currentQuestion = window.currentGameData.current_black_card;
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

function displayState(game) {
    var gameState = game.state;
    gameLobbyContent.classList.add('hidden');
    gamePlayContent.classList.add('hidden');
    gameEndContent.classList.add('hidden');
    czarWaitingPhase.classList.add('hidden');

    if(gameState === 'lobby') {
        // show lobby elements: players, spectators, settings, for creator: start button
        gameLobbyContent.classList.remove('hidden');
    } else if(gameState === 'choosing_cards' || gameState === 'choosing_winner' || gameState === 'countdown_next_round') {
        // show gameplay elements: question, timer, czar, player status, hand (if not spectator)
        gamePlayContent.classList.remove('hidden');
        // only czar and spectator
        if(gameState === 'choosing_cards' && (game.czar == window.currentUsername || game.spectators.includes(window.currentUsername))) {
            czarWaitingPhase.classList.remove('hidden');
        }
    } else if(gameState === 'game_ended') {
        // show endgame elements: final scores, winner, history, back to lobby button
        gameEndContent.classList.remove('hidden');
    }
}

function updateGameState_Lobby(game) {
    displayState(game);
    // need: gametitle, players, owner, spectators, creator, player-status, settings, game-invite-link
    update_titleLobby(game);
    updateLobbyPlayerList(game);
    update_settingsLobby(game);
    update_joinlink(game);
}

function updateGameState_ChoosingCards(game) {
    displayState(game);
    // need: czar, owner, question, timer, hand (if not spectator), player(-status), gamesettings(max punkte, max runden)
    update_ownerControls(game);
    update_pauseOverlay(game.paused);
    update_titleLobby(game);
    update_czarInfo(game);
    update_question(game);
    update_timer(game);
    update_scores(game);

    if(game.czar == window.currentUsername || game.spectators.includes(window.currentUsername)) {
        update_czarDeliveryInfo(Object.keys(game.submitted_white_cards).length, game.active_players.length-1);
    } else {
        if(window.currentUsername in game.submitted_white_cards) {
            answerPhase.classList.add('hidden');
            waitingVotePhase.classList.remove('hidden');
        } else {
            answerPhase.classList.remove('hidden');    
            update_gamehands(game);
        }
    }
    resultPhase.classList.add('hidden');
}

function updateGameState_ChooseingWinner(game) {
    displayState(game);
    // need: czar, owner, question, answer-options, timer, player(-status), gamesettings(max punkte, max runden),
    update_ownerControls(game);
    update_pauseOverlay(game.paused);
    update_titleLobby(game);
    update_czarInfo(game);
    update_question(game);
    update_timer(game);
    update_scores(game);
    update_czarSelection(game);

    selectedCards = [];
    currentHand = [];

    answerPhase.classList.add('hidden');
    czarWaitingMessage.classList.add('hidden');
    waitingVotePhase.classList.add('hidden');
    resultPhase.classList.add('hidden');
}

function updateGameState_CountdownNextRound(game) {
    displayState(game);
    // need: czar, owner, question, winning-answer, timer, player(-status), gamesettings(max punkte, max runden),
    update_ownerControls(game);
    update_pauseOverlay(game.paused);
    update_titleLobby(game);
    update_czarInfo(game);
    update_question(game);
    update_timer(game);
    update_scores(game);
    update_resultPhase(game);

    votingPhase.classList.add('hidden');
}

function updateGameState_GameEnded(game) {
    displayState(game);
    // need: owner, final-scores, winner, player(-status), gamesettings(max punkte, max runden),
    update_ownerControls(game);
    update_titleLobby(game);
    update_scores(game);
    update_gameEnd(game);
    
    resultPhase.classList.add('hidden');
}

function update_gameEnd(game) {
    // Build winners array and sort by score descending
    let sortedScores = Object.entries(game.scores)
        .sort((a, b) => b[1] - a[1])
        .map(([player, score]) => [player, score]);

    let playerColor = generatePlayerColor(sortedScores[0][0]);
    gameWinner.innerHTML = `<span class="player-badge" style="background-color: ${playerColor.bgColor}; color: ${playerColor.textColor};">${escapeHtml(sortedScores[0][0])}</span>`;

    finalScores.innerHTML = '';
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

    displayRoundHistory(game.history);

}

function update_resultPhase(game) {
    resultPhase.classList.remove('hidden');
    
    let questionText = game.current_black_card.card_text;
    let winning_white_cards = game.winning_white_cards;
    let winningUsername = winning_white_cards.playerName;
    let winningAnswers = winning_white_cards.cards;

    // Ersetze jedes "_____" durch die entsprechende Antwort
    winningAnswers.forEach(answer => {
        questionText = questionText.replace('_____', `<strong class="filled-answer">${answer}</strong>`);
    });
    resultQuestion.innerHTML = questionText;
    
    // Triggere Schaukel-Animation
    resultQuestion.classList.add('winner-flip');

    if(window.currentUsername === winningUsername) {
        roundWinner.textContent = "Du gewinnst diese Runde!";
        showNotification(`Du gewinnst diese Runde!`, 'success');
    } else {
        var playerColor = generatePlayerColor(winningUsername);
        roundWinner.innerHTML = `<span class="player-badge" style="background-color: ${playerColor.bgColor}; color: ${playerColor.textColor};">${escapeHtml(winningUsername)}</span> gewinnt diese Runde!`;
        showNotification(`${escapeHtml(winningUsername)} gewinnt diese Runde!`, 'success');
    }
}

function update_ownerControls(game) {
    let isOwner = window.currentUsername === game.owner;
    gameControls.classList.toggle('hidden', !isOwner);
}

function update_czarSelection(game) {

    //console.log("display czar selection", game.submitted_white_cards);
    
    votingPhase.classList.remove('hidden');
    answerOptionsList.innerHTML = '';
    let isCzar = (game.czar == window.currentUsername);
    let submitted_options = game.submitted_white_cards;
    let playermapping = game.player_mapping;
    let currentQuestion = game.current_black_card;

    votingPhaseTitle.textContent = isCzar ?
        'Wähle die beste Antwort!' :
        'Warte während der Czar am auswählen ist...';

    for (const i in playermapping) {
        // Finde die Option, die zu diesem Spieler gehört
        let playerName = playermapping[i];
        //console.log("playerName:", playerName);
        let cards = submitted_options[playerName];

        const optionEl = document.createElement('div');
        optionEl.className = 'answer-option';
        if (!isCzar) {
            optionEl.classList.add('readonly');
        }

        const answerText = currentQuestion.card_text;
        let filledText = answerText;
        
        cards.forEach((answer, i) => {
            filledText = filledText.replace('_____', `<strong>${escapeHtml(answer)}</strong>`);
        });
        
        optionEl.innerHTML = `<div class="answer-text">${filledText}</div>`;
        
        if (isCzar) {
            optionEl.addEventListener('click', () => selectWinner(i, optionEl));
        }
        answerOptionsList.appendChild(optionEl);

    }
}


function selectWinner(index, optionEl) {
    
    // Blockiere während Pause
    if (window.currentGameData.paused) {
        return;
    }
    
    document.querySelectorAll('.answer-option').forEach(el => {
        el.classList.remove('selected-winner');
        el.classList.remove('winner-flip');
    });
    optionEl.classList.add('selected-winner');
    optionEl.classList.add('winner-flip');
    
    socket.emit('vote_winner', { winner_index: parseInt(index) });
}


function update_czarInfo(game) {
    // den czar text aktualisieren "Du bist Czar", "Card Czar: XYZ" etc.
    let czar = game.czar;
    if(czar == window.currentUsername) {
        czarInfo.innerText = "Du bist der Card Czar dieser Runde!";
    } else {
        czarInfo.innerText = `Card Czar: ${czar}`;
    }
}

function update_question(game) {
    // die frage im schwarzen kasten aktualisieren
    let black_card = game.current_black_card;

    questionText.innerHTML = black_card["card_text"].replace(/_____/g, '<span class="blank">_____</span>');
    cardsNeeded.textContent = black_card.num_blanks;
    selectionMax.textContent = black_card.num_blanks;
    
}

function update_timer(game) {
    // der timer falls existiert aktualisieren oder ausblenden
    updateTimerDisplay(game.currentTimerSeconds, game.currentTimerTotalSeconds);
}

function update_scores(game) {
    // scores unter der frage + wann gewonnen text
    const maxRounds = game.settings["maxRounds"] || 50;
    const currentRound = game.current_round + 1;
    const winScore = game.settings["maxPointsToWin"] || 10;
    winScoreLabel.textContent = `Spiel bis ${winScore} Punkte oder Runde ${currentRound}/${maxRounds}`;
    winScoreLabel.style.display = 'block';

    scoresPanel.innerHTML = '';
    const maxScore = Math.max(...Object.values(game.scores));

    for (const [player, score] of Object.entries(game.scores)) {
        const item = document.createElement('div');
        item.className = 'score-item';
        if (score === maxScore && score > 0) {
            item.classList.add('leading');
        }

        let status = game.player_status[player];

        let statusIcon = '';
        if (status === 'disconnecting') {
            statusIcon = '<span class="status-indicator disconnecting" title="Verbindung unterbrochen...">⏳</span>';
        } else if (status === 'connected') {
            statusIcon = '<span class="status-indicator connected" title="Verbunden">●</span>';
        }

        item.innerHTML = `
            ${statusIcon}
            <span class="score-name">${escapeHtml(player)}</span>
            <span class="score-value">${score}</span>
        `;
        
        // Wende Spielerfarbe an
        applyPlayerColor(item, player);
        
        scoresPanel.appendChild(item);
    }
}


function update_gamehands(game) {
    // only update hands if hands are presented in new game data and use local currentHand to avoid overwriting selected cards
    if(game.currentPlayerCards) {
        currentHand = game.currentPlayerCards;
    }

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



function update_titleLobby(game) {
    gameTitle.textContent = game.settings.gameName;
}

function update_settingsLobby(game) {
    // Lade Settings über game-settings.js
    if (window.gameSettings) {
        window.gameSettings.load(game);
        window.gameSettings.updateAccess(game.owner === window.currentUsername);
    }
}

function update_joinlink(game) {
    // Update join link
    const joinUrl = `${window.location.origin}?join=${game.game_id}`;
    joinLinkInput.value = joinUrl;
}


// ########################################
//
//       Update Game Room
//
// ########################################
// Zeige basierend auf Game-State die richtigen UI-Elemente an
function updateGameRoom(game) {
    let state = game.state; // 'lobby', 'choosing_cards', 'choosing_winner', 'countdown_next_round', 'game_ended'
    if(state === 'lobby') {
        // zeig die lobby und aktualisiere die spielerliste, einstellungen usw.
        updateGameState_Lobby(game);
    } else if(state === "choosing_cards") {
        // zeig jedem spieler für die kartenwahl seine karten die frage usw.
        updateGameState_ChoosingCards(game);
    } else if(state === "choosing_winner") {
        // zeig jedem spieler die abgegebenen antworten in die frage integriert und lass den czar den gewinner wählen
        updateGameState_ChooseingWinner(game);
    } else if(state === "countdown_next_round") {
        // zeig jedem die gewonnene karte und den punktestand, bereite die nächste runde vor mit zentralem countdown
        updateGameState_CountdownNextRound(game);
    } else if(state === "game_ended") {
        // zeig jedem den endstand und den gewinner des spiels sowie history mit button für neues spiel
        updateGameState_GameEnded(game);
    }
}


socket.on('game_reset_to_lobby', (game) => {
    // Zurück zur Game-Lobby
    showNotification('Spiel wurde zurückgesetzt', 'info');
    window.currentGameData = game;
    updateGameRoom(game);
});


function updateLobbyPlayerList(game) {
    //console.log("updateLobbyPlayerList:", game.active_players, game.spectators);

    let player_status = game.player_status || {};
    let spectators = game.spectators || [];
    let active_players = game.active_players || [];

    let allMembers = active_players.slice();
    allMembers = allMembers.concat(spectators);

    playersList.innerHTML = '';
    spectatorsList.innerHTML = '';

    spectatorsSection.classList.toggle('hidden', spectators.length === 0);

    allMembers.forEach(player => {
        
        let isCreator = (player == window.currentUsername);
        let isCurrentPlayer = (player == window.currentUsername);
        let isSpectator = spectators.includes(player);
        let connection_status = player_status[player] || 'connected';
        let canKick = (game.owner == window.currentUsername) && (player != window.currentUsername);
        let canForceRole = (game.owner == window.currentUsername) && (player != window.currentUsername);

        let listObject = createListObject(player, isCreator, isCurrentPlayer, isSpectator, connection_status, canKick, canForceRole);

        if (isSpectator) {
            spectatorsList.appendChild(listObject);
        } else {
            playersList.appendChild(listObject);
        }
    });
}

function createListObject(name, isCreator, isCurrentPlayer, isSpectator, connection_status, canKick, canForceRole) {
    const item = document.createElement('div');
    item.className = 'player-item' + (isSpectator ? ' spectator-item' : '');
    if(isCreator) {
        item.classList.add('creator');
    }
    if(isCurrentPlayer) {
        item.classList.add('current-player');
    }

    // Status-Indikator
    let statusIcon = '';
    if (connection_status === 'disconnecting') {
        statusIcon = '<span class="status-indicator disconnecting" title="Verbindung unterbrochen...">⏳</span>';
    } else if (connection_status === 'connected') {
        statusIcon = '<span class="status-indicator connected" title="Verbunden">●</span>';
    }

    // Kick-Button für Creator (nur wenn nicht selbst, nicht Creator und nicht gestartet)
    let kickButton = '';
    if (canKick) {
        kickButton = `<button class="btn-kick" onclick="kickPlayer('${escapeHtml(name).replace(/'/g, "\\'")}')">Kick</button>`;
    }
    // Force-Role Button für Creator bei anderen Spielern (nur in Lobby)
    let forceRoleButton = '';
    if (canForceRole) {
        forceRoleButton = `<button class="btn-force-role" onclick="forceRole('${escapeHtml(name).replace(/'/g, "\\'")}')\" title="Zu Zuschauer verschieben">👁️</button>`;
    }

    // Toggle zu Spieler für eigenen Spectator (nicht während Spiel läuft)
    let toggleButton = '';
    if (isCurrentPlayer) {
        toggleButton = `<button class="btn-toggle-role" onclick="toggleRole()" title="Zu Spieler wechseln">🎮</button>`;
    }

        
    item.innerHTML = `
        <span>${statusIcon}${isCurrentPlayer ? '(Du)' : ''} ${escapeHtml(name)}</span>
        <span class="player-actions">
            ${isCreator? '<span class="crown">👑</span>' : ''}
            ${toggleButton}
            ${forceRoleButton}
            ${kickButton}
        </span>
    `;

    // Wende Spielerfarbe an
    applyPlayerColor(item, name);
    return item;
}



function displayRoundHistory(history) {
    const container = document.getElementById('round-history-container');
    if (!container) return;
    
    container.innerHTML = '';
    
    if (history.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: #999;">Keine Runden gespielt???</p>';
        return;
    }
    
    // Zeige Runden in umgekehrter Reihenfolge (neueste zuerst)
    history.slice().reverse().forEach((round) => {
        const card = document.createElement('div');
        card.className = 'history-card';
        
        // Fülle die Frage mit den gewinnenden Antworten
        let filledQuestion = round.black_card.card_text;

        for(let i=0; i<round.winning_cards.length; i++) {
            filledQuestion = filledQuestion.replace('_____', `<span class="filled-answer">${round.winning_cards[i]}</span>`);
        }

        const czarColors = generatePlayerColor(round.czar || '[AUTOMATIC]');
        const winnerColors = generatePlayerColor(round.playerName);
        
        card.innerHTML = `
            <div class="history-card-header">
                <span class="round-number">Runde ${round.round+1}</span>
            </div>
            <div class="history-question-filled">
                ${filledQuestion}
            </div>
            <div class="history-meta">
                <div class="history-meta-item">
                    <span>👑</span>
                    <span class="player-badge" style="background-color: ${czarColors.bgColor}; color: ${czarColors.textColor};"><strong>${escapeHtml(round.czar || '[AUTOMATIC]')}</strong></span>
                </div>
                <div class="history-meta-item">
                    <span>🏆</span>
                    <span class="player-badge" style="background-color: ${winnerColors.bgColor}; color: ${winnerColors.textColor};"><strong>${escapeHtml(round.playerName)}</strong></span>
                </div>
            </div>
        `;
        
        container.appendChild(card);
    });
}

const toggleLinkBtn = document.getElementById('toggle-link-btn');
let linkVisible = false;
toggleLinkBtn.addEventListener('click', function() {
    setInviteLinkVisibility(!linkVisible);
});

function setInviteLinkVisibility(visible) {
    linkVisible = visible;
    if (linkVisible) {
        joinLinkInput.type = 'text';
        toggleLinkBtn.textContent = 'Verstecken';
    } else {
        joinLinkInput.type = 'password';
        toggleLinkBtn.textContent = 'Anzeigen';
    }
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
    window.currentGameData = data.game;
    updateGameRoom(data.game);
    
    // Notification
    if (data.username === window.currentUsername) {
        if (data.forced_by) {
            showNotification(`Deine Rolle wurde von ${data.forced_by} zu ${data.role} geändert`, 'warning');
        } else {
            showNotification(`Du bist jetzt ${data.role}`, 'success');
        }
    } else {
        showNotification(`${data.username} ist jetzt ${data.role}`, 'info');
    }
});

socket.on('game_started', (game) => {
    // Update Creator info
    window.currentGameData = game;
    updateGameRoom(game);
});

socket.on('left_game', () => {
    window.currentGameData = null;
    window.ui.showServerLobby();
});

// Player submitted
socket.on('player_submitted', (data) => {
    // Czar und Spectator sehen zusätzlich den Abgabestatus
    update_czarDeliveryInfo(data.submitted_count, data.total_players);
    showNotification(`${data.username} hat abgegeben`, 'info');
});

function update_czarDeliveryInfo(submitted_count, total_players) {
    submissionStatus.textContent = `${submitted_count} von ${total_players} Spielern haben abgegeben`;
}

window.ui.showGameScreen = showGameScreen;