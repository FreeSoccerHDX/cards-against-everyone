let wakeLock = null;

async function enableWakeLock() {
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
