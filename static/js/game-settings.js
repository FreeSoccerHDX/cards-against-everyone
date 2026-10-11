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

// Wegwerfrunde
const settingsDiscardRoundActive = document.getElementById('settings-discard-round-active');
const settingsDiscardRoundInterval = document.getElementById('settings-discard-round-interval');
const settingsDiscardMaxCards = document.getElementById('settings-discard-max-cards');
const settingsDiscardTime = document.getElementById('settings-discard-time');


const settingsInputs = document.querySelectorAll('.settings-input');

// Auto-Save Mechanismus für Settings
let settingsTimeout = null;

// Zahl aus Input lesen; ungültige Werte (außerhalb min/max) werden nicht gesendet
function readNumber(input) {
    const value = parseInt(input.value);
    return (Number.isNaN(value) || !input.checkValidity()) ? null : value;
}

function autoSaveSettings() {

    clearTimeout(settingsTimeout);
    settingsTimeout = setTimeout(() => {
        const settingsData = {
            gameName: settingsName.value.trim() || null,
            publicVisible: settingsPublic.checked,
            publicVisibleDuringGame: settingsPublicDuringGame.checked,
            password: settingsPassword.value.trim(),
            maxPlayers: readNumber(settingsMaxPlayers),
            maxWhiteCardsPerPlayer: readNumber(settingsMaxCards),
            maxPointsToWin: readNumber(settingsWinScore),
            maxRounds: readNumber(settingsMaxRounds),
            timeToChooseWhiteCards: readNumber(settingsAnswerTime),
            timeToChooseWinner: readNumber(settingsCzarTime),
            timeAfterWinnerChosen: readNumber(settingsRoundDelay),
            discardRoundActive: settingsDiscardRoundActive.checked,
            discardRoundInterval: readNumber(settingsDiscardRoundInterval),
            discardMaxCards: readNumber(settingsDiscardMaxCards),
            discardTime: readNumber(settingsDiscardTime)
            
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
    settingsDiscardRoundActive.addEventListener('change', autoSaveSettings);
    settingsDiscardRoundInterval.addEventListener('input', autoSaveSettings);
    settingsDiscardMaxCards.addEventListener('input', autoSaveSettings);
    settingsDiscardTime.addEventListener('input', autoSaveSettings);
    
    // Start Game Button
    startGameBtn.addEventListener('click', () => {
        if (window.socket) {
            window.socket.emit('start_game');
        }
    });
}

// Funktion um Settings-Werte aus einem Game-Objekt zu laden
function loadGameSettings(game) {
    // Feld, in dem der Owner gerade tippt, nicht überschreiben
    const focused = document.activeElement;
    const set = (input, value) => { if (input !== focused) input.value = value; };

    set(settingsName, game.settings.gameName);
    settingsPublic.checked = game.settings.publicVisible;
    set(settingsPassword, game.settings.password || '');
    set(settingsMaxCards, game.settings.maxWhiteCardsPerPlayer);
    set(settingsWinScore, game.settings.maxPointsToWin || 5);
    set(settingsMaxRounds, game.settings.maxRounds || 25);
    set(settingsAnswerTime, game.settings.timeToChooseWhiteCards || 60);
    set(settingsCzarTime, game.settings.timeToChooseWinner || 60);
    set(settingsRoundDelay, game.settings.timeAfterWinnerChosen || 15);
    set(settingsMaxPlayers, game.settings.maxPlayers || 10);
    settingsPublicDuringGame.checked = game.settings.publicVisibleDuringGame || false;
    settingsDiscardRoundActive.checked = game.settings.discardRoundActive || false;
    set(settingsDiscardRoundInterval, game.settings.discardRoundInterval || 10);
    set(settingsDiscardMaxCards, game.settings.discardMaxCards || 3);
    set(settingsDiscardTime, game.settings.discardTime || 30);
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
