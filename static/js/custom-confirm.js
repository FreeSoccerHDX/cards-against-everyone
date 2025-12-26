// Custom Confirm Dialog
function customConfirm(message, title = 'Bestätigung erforderlich') {
    return new Promise((resolve) => {
        const overlay = document.getElementById('custom-confirm-overlay');
        const titleEl = document.getElementById('custom-confirm-title');
        const messageEl = document.getElementById('custom-confirm-message');
        const okBtn = document.getElementById('custom-confirm-ok');
        const cancelBtn = document.getElementById('custom-confirm-cancel');
        
        titleEl.textContent = title;
        messageEl.textContent = message;
        overlay.classList.add('active');
        
        const handleOk = () => {
            cleanup();
            resolve(true);
        };
        
        const handleCancel = () => {
            cleanup();
            resolve(false);
        };
        
        const handleEscape = (e) => {
            if (e.key === 'Escape') {
                handleCancel();
            }
        };
        
        const cleanup = () => {
            overlay.classList.remove('active');
            okBtn.removeEventListener('click', handleOk);
            cancelBtn.removeEventListener('click', handleCancel);
            document.removeEventListener('keydown', handleEscape);
        };
        
        okBtn.addEventListener('click', handleOk);
        cancelBtn.addEventListener('click', handleCancel);
        document.addEventListener('keydown', handleEscape);
    });
}
