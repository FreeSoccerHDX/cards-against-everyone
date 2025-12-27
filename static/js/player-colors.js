// Player Color System
const playerColors = {};

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
    // Wenn Helligkeit unter 60% ist, nutze weiß, sonst schwarz
    const oppositeHue = (h + 180) % 360;
    const oppositeColor = `hsl(${oppositeHue}, ${s}%, ${l}%)`;
    return oppositeColor;
    //return l < 60 ? '#ffffff' : '#000000';
}

function applyPlayerColor(element, username) {
    const colors = generatePlayerColor(username);
    element.style.backgroundColor = colors.bgColor;
    element.style.color = colors.textColor;
}
