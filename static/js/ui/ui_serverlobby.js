

const lobbyScreen = document.getElementById('lobby-screen');
const refreshGamesBtn = document.getElementById('refresh-games-btn');

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


refreshGamesBtn.addEventListener('click', () => {
    getGameLobbys();
});

window.socket.on('public_games', (data) => {
    displayPublicGames(data.games);
});


window.ui.showServerLobby = showServerLobby; 