const userSettingsButton = document.getElementById('user-settings-button');
const userSettingsModal = document.getElementById('user-settings-modal');
const userSettingsClose = document.getElementById('user-settings-close');
const darkModeToggle = document.getElementById('dark-mode-toggle');

const sliderVolume = document.getElementById("volume");
const outputVolumeValue = document.getElementById("volumeValue");

var currentVolume = localStorage.getItem("volume") || 50;

sliderVolume.addEventListener("input", (event) => {
    const value = parseInt(event.target.value, 10);
    outputVolumeValue.textContent = value;

    currentVolume = value;
    localStorage.setItem("volume", currentVolume);
});

userSettingsButton.addEventListener('click', () => {
    window.ui.showModal(userSettingsModal);
});

userSettingsClose.addEventListener('click', () => {
    window.ui.hideModal(userSettingsModal);
});

// Hide the original toggle
darkModeToggle.style.display = 'none';

// Load dark mode setting from localStorage, default to true if not set
let darkModeEnabled = localStorage.getItem('darkMode');
if (darkModeEnabled === null) {
    darkModeEnabled = 'true';
    localStorage.setItem('darkMode', 'true');
}
darkModeToggle.checked = darkModeEnabled === 'true';
if (darkModeToggle.checked) {
    document.body.classList.add('darkmode');
} else {
    document.body.classList.remove('darkmode');
}

// Listen for changes and toggle dark mode colors
darkModeToggle.addEventListener('change', function() {
    if (darkModeToggle.checked) {
        document.body.classList.add('darkmode');
        localStorage.setItem('darkMode', 'true');
    } else {
        document.body.classList.remove('darkmode');
        localStorage.setItem('darkMode', 'false');
    }
});

const switchContainer = document.createElement('label');
switchContainer.className = 'switch';
switchContainer.innerHTML = `
    <input type="checkbox" id="dark-mode-toggle-real">
    <span class="slider"></span>
`;
darkModeToggle.parentNode.insertBefore(switchContainer, darkModeToggle);
switchContainer.appendChild(darkModeToggle);

const realToggle = document.getElementById('dark-mode-toggle-real');
realToggle.checked = darkModeToggle.checked;
realToggle.addEventListener('change', function() {
    darkModeToggle.checked = realToggle.checked;
    darkModeToggle.dispatchEvent(new Event('change'));
});
const toggle = document.getElementById('dark-mode-toggle');
const label = document.getElementById('dark-mode-label');
function updateLabel() {
    label.textContent = toggle.checked ? 'Dark Mode' : 'Light Mode';
}
toggle.addEventListener('change', updateLabel);
updateLabel();