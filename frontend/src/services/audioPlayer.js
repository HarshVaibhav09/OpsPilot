// Browsers block programmatic audio playback unless it traces back to a
// user gesture. Our playback happens after an async round-trip, so by
// then the gesture is long gone. The fix is to create and "arm" a single
// Audio element during the user's first click, then reuse that same
// element for every later playback.

let audioElement = null;
let currentUrl = null;

export function unlockAudio() {
  if (audioElement) return;

  audioElement = new Audio();

  // Playing (and immediately pausing) inside the click handler marks the
  // element as user-activated for the rest of the session.
  audioElement.play().catch(() => {
    // Expected: there is no source yet. The element is now armed anyway.
  });

  audioElement.pause();
}

export function stopAudio() {
  if (!audioElement) return;

  audioElement.pause();
  audioElement.currentTime = 0;
}

export function playAudioBlob(blob) {
  return new Promise((resolve, reject) => {
    if (!audioElement) {
      audioElement = new Audio();
    }

    stopAudio();

    if (currentUrl) {
      URL.revokeObjectURL(currentUrl);
    }

    currentUrl = URL.createObjectURL(blob);
    audioElement.src = currentUrl;

    function cleanup() {
      audioElement.onended = null;
      audioElement.onerror = null;

      if (currentUrl) {
        URL.revokeObjectURL(currentUrl);
        currentUrl = null;
      }
    }

    audioElement.onended = () => {
      cleanup();
      resolve();
    };

    audioElement.onerror = () => {
      cleanup();
      reject(new Error("Audio playback failed."));
    };

    audioElement.play().catch((error) => {
      cleanup();
      reject(error);
    });
  });
}