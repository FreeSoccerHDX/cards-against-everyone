const createGameModal = document.getElementById('create-game-modal');

const gameNameInput = document.getElementById('game-name-input');
const gamePublicCheckbox = document.getElementById('game-public-checkbox');
const gamePasswordInput = document.getElementById('game-password-input');
const createGameConfirm = document.getElementById('create-game-confirm');
const createGameCancel = document.getElementById('create-game-cancel');


function showCreateGameModal() {
    window.ui.hideAllModals(); // es kann kein anderes Modal offen sein

    gameNameInput.value = `${window.currentUsername}'s Spiel`;
    gamePublicCheckbox.checked = true;
    gamePasswordInput.value = '';

    window.ui.showModal(createGameModal);
}

function hideCreateGameModal() {
    window.ui.hideModal(createGameModal);
}


createGameConfirm.addEventListener('click', () => {
    const name = gameNameInput.value.trim() || 'Neues Spiel';
    const isPublic = gamePublicCheckbox.checked;
    const password = gamePasswordInput.value.trim();
    
    socket.emit('create_game', {
        name: name,
        is_public: isPublic,
        password: password
    });
    
    window.ui.hideCreateGameModal();
});



createGameCancel.addEventListener('click', () => {
    window.ui.hideCreateGameModal();
});


window.ui.showCreateGameModal = showCreateGameModal;
window.ui.hideCreateGameModal = hideCreateGameModal;
