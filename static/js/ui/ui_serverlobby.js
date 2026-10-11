

const lobbyScreen = document.getElementById('lobby-screen');
const refreshGamesBtn = document.getElementById('refresh-games-btn');
const createGameBtn = document.getElementById('create-game-btn');
const logoutBtn = document.getElementById('logout-btn');

const currentUsernameDisplay = document.getElementById('current-username');
const publicGamesDiv = document.getElementById('public-games');

const gameSearchInput = document.getElementById('game-search-input');
gameSearchInput.addEventListener('input', () => {
    const filter = gameSearchInput.value.toLowerCase();
    const gameCards = publicGamesDiv.getElementsByClassName('game-card');
    Array.from(gameCards).forEach(card => {
        const gameName = card.querySelector('h3').textContent.toLowerCase();
        if (gameName.includes(filter)) {
            card.style.display = '';
        } else {
            card.style.display = 'none';
        }
    });

    displayPublicGames();
});


function showServerLobby() {
    window.ui.showScreen(lobbyScreen);

    getGameLobbys();
}

function getGameLobbys() {
    socket.emit('get_public_games');
}

var lastSavedGames = [];

function displayPublicGames(_games) {
    if(_games !== undefined) {
        lastSavedGames = _games;
    }
    
    let filteredGames = lastSavedGames;
    
    const filter = gameSearchInput.value.toLowerCase();
    if (filter) {
        filteredGames = lastSavedGames.filter(game => 
            (game.name.toLowerCase().includes(filter) || game.is_pending)
        );
    }

    if (!filteredGames || filteredGames.length === 0) {
        publicGamesDiv.innerHTML = '<p class="empty-message">Keine öffentlichen Spiele verfügbar</p>';
        return;
    }
    
    publicGamesDiv.innerHTML = '';
    filteredGames.forEach(game => {
        let gameStarted = game.started || false;

        const card = document.createElement('div');
        card.className = 'game-card';
        if(game.is_pending) {
            card.classList.add('pending-game');
        }
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
        // Lösche gespeichertes Token, Server gibt Namen frei und verlässt ggf. das Spiel
        clearSavedToken();
        window.currentGameData = null;
        socket.emit('logout');
        
        // Reset Zustand
        window.currentUsername = null;
        
        // Gehe zu Username-Screen
        window.ui.showLoginScreen();
        usernameInput.value = '';
        usernameError.textContent = '';

        getRandomFunnyName();
        
        showNotification('Abgemeldet', 'info');
    }
});



window.ui.showServerLobby = showServerLobby; 