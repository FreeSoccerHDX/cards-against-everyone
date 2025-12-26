const joinGameModal = document.getElementById('join-game-modal');

const joinGameName = document.getElementById('join-game-name');

const joinAsSpectatorCheckbox = document.getElementById('join-as-spectator');

const joinPasswordGroup = document.getElementById('join-password-group');
const joinPasswordInput = document.getElementById('join-password-input');

const joinGameConfirm = document.getElementById('join-game-confirm');
const joinGameCancel = document.getElementById('join-game-cancel');

var selectedGameForJoin = null;

function showJoinGameModal(game) {
    window.ui.hideAllModals(); // es kann kein anderes Modal offen sein

    selectedGameForJoin = game;

    let gameStarted = game.started || false;
    
    joinGameName.textContent = `Beitritt zu: ${game.name}${gameStarted ? ' (läuft bereits)' : ''}`;

    if (game.has_password) {
        joinPasswordGroup.style.display = 'block';
        joinPasswordInput.value = '';
    } else {
        joinPasswordGroup.style.display = 'none';
    }

    showModal(joinGameModal);
}

function hideJoinGameModal() {
    window.ui.hideModal(joinGameModal);

    // Spectator-Checkbox zurücksetzen
    joinAsSpectatorCheckbox.checked = false;

    // Passwortfeld zurücksetzen
    joinPasswordGroup.style.display = 'none';
    joinPasswordInput.value = '';
}



joinGameConfirm.addEventListener('click', () => {
    const password = joinPasswordInput.value.trim();
    const isSpectator = joinAsSpectatorCheckbox.checked;
    
    socket.emit('join_game', {
        game_id: selectedGameForJoin.id,
        password,
        is_spectator: isSpectator
    });
    
    
    window.ui.hideJoinGameModal();
});

joinGameCancel.addEventListener('click', () => {
    window.ui.hideJoinGameModal();
    selectedGameForJoin = null;
});

window.ui.showJoinGameModal = showJoinGameModal;
window.ui.hideJoinGameModal = hideJoinGameModal;