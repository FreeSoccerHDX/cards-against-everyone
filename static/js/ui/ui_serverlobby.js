

const lobbyScreen = document.getElementById('lobby-screen');
const refreshGamesBtn = document.getElementById('refresh-games-btn');
const createGameBtn = document.getElementById('create-game-btn');
const logoutBtn = document.getElementById('logout-btn');

const currentUsernameDisplay = document.getElementById('current-username');
const publicGamesDiv = document.getElementById('public-games');

function showServerLobby() {
    window.ui.showScreen(lobbyScreen);

    getGameLobbys();
}

function getGameLobbys() {
    socket.emit('get_public_games');
}

function displayPublicGames(games) {
    if (!games || games.length === 0) {
        publicGamesDiv.innerHTML = '<p class="empty-message">Keine öffentlichen Spiele verfügbar</p>';
        return;
    }
    
    publicGamesDiv.innerHTML = '';
    games.forEach(game => {
        let gameStarted = game.started || false;

        const card = document.createElement('div');
        card.className = 'game-card';
        card.innerHTML = `
            <h3>${escapeHtml(game.name)} ${gameStarted ? '(Laufendes Spiel)' : ''}</h3>
            <div class="game-info">
                <span>👥 ${game.players} Spieler</span>
                ${game.has_password ? '<span class="lock-icon">🔒</span>' : ''}
            </div>
        `;
        card.addEventListener('click', () => {
            window.ui.showJoinGameModal(game);
        });
        publicGamesDiv.appendChild(card);
    });
}


// Lobby - Create Game
createGameBtn.addEventListener('click', () => {
    window.ui.showCreateGameModal();
});

refreshGamesBtn.addEventListener('click', () => {
    getGameLobbys();
});

window.socket.on('public_games_list', (data) => {
    displayPublicGames(data.games);
});

// Lobby - Logout-Button
logoutBtn.addEventListener('click', async () => {
    if (await customConfirm('Möchtest du dich wirklich abmelden?', 'Abmelden')) {
        // Lösche gespeicherten Username
        clearSavedUsername();
        
        // Verlasse ggf. Spiel
        if (currentGameId) {
            socket.emit('leave_game');
        }
        
        // Reset Zustand
        window.currentUsername = null;
        currentGameId = null;
        currentGameCreator = null;
        setIsCreator(false);
        
        // Gehe zu Username-Screen
        window.ui.showLoginScreen();
        usernameInput.value = '';
        usernameError.textContent = '';
        
        showNotification('Abgemeldet', 'info');
    }
});



window.ui.showServerLobby = showServerLobby; 