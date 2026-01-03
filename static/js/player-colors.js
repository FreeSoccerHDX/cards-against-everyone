// Player Color System
const playerColors = {};

const playerNameColors = [
  { background: "#195f9cff", text: "#FFFFFF" }, // Blau
  { background: "#992525ff", text: "#FFFFFF" }, // Rot
  { background: "#388E3C", text: "#FFFFFF" }, // Grün
  { background: "#FBC02D", text: "#000000" }, // Gelb
  { background: "#7B1FA2", text: "#FFFFFF" }, // Lila
  { background: "#00796B", text: "#FFFFFF" }, // Türkis
  { background: "#a35a11ff", text: "#000000" }, // Orange
  { background: "#455A64", text: "#FFFFFF" }, // Blaugrau
  { background: "#e74485ff", text: "#FFFFFF" }, // Pink
  { background: "#8c9102ff", text: "#000000" }  // Oliv
];

function hashCode(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        const char = str.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash;
    }
    return Math.abs(hash);
}

function generatePlayerColor(username) {
    if (playerColors[username]) {
        return playerColors[username];
    }
    if(true) {
        const index = hashCode(username) % playerNameColors.length;
        const colors = playerNameColors[index];
        playerColors[username] = { bgColor: colors.background, textColor: colors.text };
        return playerColors[username];
    }
    
    const hash = hashCode(username);
    const hue = hash % 360;
    const saturation = 65 + (hash % 20);
    const lightness = 55 + (hash % 15);
    
    const bgColor = `hsl(${hue}, ${saturation}%, ${lightness}%)`;
    const textColor = getContrastColor(hue, saturation, lightness);
    
    playerColors[username] = { bgColor, textColor };
    return playerColors[username];
}

function getContrastColor(h, s, l) {
    // 1. Hue um 180° drehen
    const oppositeHue = (h + 180) % 360;

    // 2. Lightness spiegeln (entscheidend für Kontrast)
    let oppositeLightness = 100 - l;

    // Extremwerte abfangen (50% ist besonders problematisch)
    if (oppositeLightness > 45 && oppositeLightness < 55) {
        oppositeLightness = l < 50 ? 85 : 15;
    }

    // 3. Sättigung stabilisieren
    let oppositeSaturation = s;
    if (oppositeSaturation < 40) {
        oppositeSaturation = 60;
    } else if (oppositeSaturation > 80) {
        oppositeSaturation = 70;
    }

    return `hsl(${oppositeHue}, ${oppositeSaturation}%, ${oppositeLightness}%)`;
}


function applyPlayerColor(element, username) {
    const colors = generatePlayerColor(username);
    element.style.backgroundColor = colors.bgColor;
    element.style.color = colors.textColor;
}
