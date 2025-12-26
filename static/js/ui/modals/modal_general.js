

function showModal(modal) {
    // Nicht alle Modals unsichtbar machen, sie könnten übereinander liegen
    modal.classList.add('active');
}

function hideModal(modal) {
    modal.classList.remove('active');
}

function hideAllModals() {
    document.querySelectorAll('.modal').forEach(modal => hideModal(modal));
}

window.ui.showModal = showModal;
window.ui.hideModal = hideModal;
window.ui.hideAllModals = hideAllModals;
