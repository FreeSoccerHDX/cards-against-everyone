// Game Settings Management
// Diese Datei verwaltet alle Spieleinstellungen und deren Auto-Save-Funktionalität

// DOM-Elemente für Settings
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

// Auto-Save Mechanismus für Settings
let settingsTimeout = null;

function autoSaveSettings() {
    console.log('autoSaveSettings called, isCreator:', window.isCreator);
    
    // Nur Creator kann Settings ändern
    if (!window.isCreator) {
        console.log('Not creator, skipping save');
        return;
    }
    
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
        console.log('Sending update_settings to server:', data);
        // Verwende socket über window
        if (window.socket) {
            window.socket.emit('update_settings', data);
        } else {
            console.error('Socket not available!');
        }
    }, 500); // 500ms Debounce
}

// Event-Listener für alle Settings-Inputs
function initializeSettingsListeners() {
    settingsName.addEventListener('input', autoSaveSettings);
    settingsPublic.addEventListener('change', autoSaveSettings);
    settingsPassword.addEventListener('input', autoSaveSettings);
    settingsMaxCards.addEventListener('input', autoSaveSettings);
    settingsWinScore.addEventListener('input', autoSaveSettings);
    settingsMaxRounds.addEventListener('input', autoSaveSettings);
    settingsAnswerTime.addEventListener('input', autoSaveSettings);
    settingsCzarTime.addEventListener('input', autoSaveSettings);
    settingsRoundDelay.addEventListener('input', autoSaveSettings);
    
    // Start Game Button
    startGameBtn.addEventListener('click', () => {
        if (window.socket) {
            window.socket.emit('start_game');
        }
    });
}

// Funktion um Settings-Werte aus einem Game-Objekt zu laden
function loadGameSettings(game) {
    settingsName.value = game.name;
    settingsPublic.checked = game.is_public;
    settingsPassword.value = game.password || '';
    settingsMaxCards.value = game.settings.max_cards;
    settingsWinScore.value = game.settings.win_score;
    settingsMaxRounds.value = game.settings.max_rounds || 50;
    settingsAnswerTime.value = game.settings.answer_time || 60;
    settingsCzarTime.value = game.settings.czar_time || 30;
    settingsRoundDelay.value = game.settings.round_delay || 5;
}

// Funktion um Settings-Inputs basierend auf Creator-Status zu aktivieren/deaktivieren
function updateSettingsAccess(isCreator) {
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
}

// Haupt-Initialisierungsfunktion - wird von script.js aufgerufen
function initializeGameSettings() {
    initializeSettingsListeners();
}

// Export für Verwendung in anderen Dateien
window.gameSettings = {
    load: loadGameSettings,
    updateAccess: updateSettingsAccess,
    initialize: initializeGameSettings
};
