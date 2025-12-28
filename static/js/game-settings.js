// Game Settings Management
// Diese Datei verwaltet alle Spieleinstellungen und deren Auto-Save-Funktionalität

// DOM-Elemente für Settings
const settingsName = document.getElementById('settings-name');
const settingsPublic = document.getElementById('settings-public');
const settingsPublicDuringGame = document.getElementById('settings-public-during-game');
const settingsPassword = document.getElementById('settings-password');
const settingsMaxCards = document.getElementById('settings-max-cards');
const settingsMaxPlayers = document.getElementById('settings-max-players');
const settingsWinScore = document.getElementById('settings-win-score');
const settingsMaxRounds = document.getElementById('settings-max-rounds');
const settingsAnswerTime = document.getElementById('settings-answer-time');
const settingsCzarTime = document.getElementById('settings-czar-time');
const settingsRoundDelay = document.getElementById('settings-round-delay');
const creatorInfo = document.getElementById('creator-info');
const startGameBtn = document.getElementById('start-game-btn');


const settingsInputs = document.querySelectorAll('.settings-input');

// Auto-Save Mechanismus für Settings
let settingsTimeout = null;

function autoSaveSettings() {

    clearTimeout(settingsTimeout);
    settingsTimeout = setTimeout(() => {
        const settingsData = {
            gameName: settingsName.value.trim(),
            publicVisible: settingsPublic.checked,
            publicVisibleDuringGame: settingsPublicDuringGame.checked,
            password: settingsPassword.value.trim(),
            maxPlayers: parseInt(settingsMaxPlayers.value),
            maxWhiteCardsPerPlayer: parseInt(settingsMaxCards.value),
            maxPointsToWin: parseInt(settingsWinScore.value),
            maxRounds: parseInt(settingsMaxRounds.value),
            timeToChooseWhiteCards: parseInt(settingsAnswerTime.value),
            timeToChooseWinner: parseInt(settingsCzarTime.value),
            timeAfterWinnerChosen: parseInt(settingsRoundDelay.value),
            
        };
        window.socket.emit('update_settings', settingsData);

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
    settingsMaxPlayers.addEventListener('input', autoSaveSettings);
    settingsPublicDuringGame.addEventListener('change', autoSaveSettings);
    
    // Start Game Button
    startGameBtn.addEventListener('click', () => {
        if (window.socket) {
            window.socket.emit('start_game');
        }
    });
}

// Funktion um Settings-Werte aus einem Game-Objekt zu laden
function loadGameSettings(game) {
    settingsName.value = game.settings.gameName;
    settingsPublic.checked = game.settings.publicVisible;
    settingsPassword.value = game.settings.password || '';
    settingsMaxCards.value = game.settings.maxWhiteCardsPerPlayer;
    settingsWinScore.value = game.settings.maxPointsToWin || 5;
    settingsMaxRounds.value = game.settings.maxRounds || 25;
    settingsAnswerTime.value = game.settings.timeToChooseWhiteCards || 60;
    settingsCzarTime.value = game.settings.timeToChooseWinner || 60;
    settingsRoundDelay.value = game.settings.timeAfterWinnerChosen || 15;
    settingsMaxPlayers.value = game.settings.maxPlayers || 10;
    settingsPublicDuringGame.checked = game.settings.publicVisibleDuringGame || false;
}

// Funktion um Settings-Inputs basierend auf Creator-Status zu aktivieren/deaktivieren
function updateSettingsAccess(isCreator) {
    settingsInputs.forEach(input => {
        input.disabled = !isCreator;
    });
    
    if (isCreator) {
        creatorInfo.classList.add('hidden');
        startGameBtn.classList.remove('hidden');
    } else {
        creatorInfo.classList.remove('hidden');
        startGameBtn.classList.add('hidden');
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
