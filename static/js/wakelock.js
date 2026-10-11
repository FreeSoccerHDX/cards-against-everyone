let wakeLock = null;

async function enableWakeLock() {
  if (!("wakeLock" in navigator)) {
    return;
  }
  try {
    wakeLock = await navigator.wakeLock.request("screen");

    wakeLock.addEventListener("release", () => {
      console.log("Wake Lock wurde freigegeben");
    });

    console.log("Wake Lock aktiv");
  } catch (err) {
    console.error(`${err.name}, ${err.message}`);
  }
}

enableWakeLock();

// Der Browser gibt den Wake Lock frei, sobald der Tab versteckt wird -> neu anfordern
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") {
    enableWakeLock();
  }
});
