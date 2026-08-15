import { useCallback, useEffect, useRef, useState } from "react";

// We deliberately ignore the browser's own end-of-speech detection.
// Chrome fires `onend` at unpredictable intervals -- sometimes cutting a
// speaker off mid-thought, sometimes hanging for seconds. Instead we run
// recognition continuously and time the gap since the last result
// ourselves, which makes the threshold a tunable product decision rather
// than a browser default.
const SILENCE_THRESHOLD_MS = 1500;
const SILENCE_CHECK_INTERVAL_MS = 200;

function getRecognitionConstructor() {
  if (typeof window === "undefined") return null;

  return (
    window.SpeechRecognition ||
    window.webkitSpeechRecognition ||
    null
  );
}

export function useSpeechRecognition({ onResult } = {}) {
  const [listening, setListening] = useState(false);
  const [interimTranscript, setInterimTranscript] = useState("");
  const [error, setError] = useState(null);

  const recognitionRef = useRef(null);
  const finalTranscriptRef = useRef("");
  const interimRef = useRef("");
  const lastResultAtRef = useRef(0);
  const silenceTimerRef = useRef(null);
  const listeningRef = useRef(false);
  const onResultRef = useRef(onResult);

  // Keep the callback fresh without re-creating the recognition object
  // every render.
  useEffect(() => {
    onResultRef.current = onResult;
  }, [onResult]);

  const supported = Boolean(getRecognitionConstructor());

  const clearSilenceTimer = useCallback(() => {
    if (silenceTimerRef.current) {
      clearInterval(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
  }, []);

  const stopListening = useCallback(
    ({ emit = false } = {}) => {
      clearSilenceTimer();
      listeningRef.current = false;

      if (recognitionRef.current) {
        recognitionRef.current.onend = null;
        recognitionRef.current.onresult = null;
        recognitionRef.current.onerror = null;

        try {
          recognitionRef.current.stop();
        } catch {
          // Already stopped -- nothing to do.
        }

        recognitionRef.current = null;
      }

      setListening(false);
      setInterimTranscript("");

      // Interim text is everything said since the last finalised result.
      // On a manual stop it has not been finalised yet, so without this
      // the user's most recent words are silently dropped.
      const transcript = `${finalTranscriptRef.current} ${interimRef.current}`
        .replace(/\s+/g, " ")
        .trim();

      finalTranscriptRef.current = "";
      interimRef.current = "";

      // An empty transcript means the mic was open but nothing was said.
      // Close quietly rather than sending an empty query downstream.
      if (emit && transcript && onResultRef.current) {
        onResultRef.current(transcript);
      }
    },
    [clearSilenceTimer]
  );

  const startListening = useCallback(() => {
    const SpeechRecognitionCtor = getRecognitionConstructor();

    if (!SpeechRecognitionCtor) {
      setError("Voice input needs Chrome or Edge.");
      return;
    }

    if (listeningRef.current) return;

    setError(null);
    setInterimTranscript("");
    finalTranscriptRef.current = "";
    interimRef.current = "";
    lastResultAtRef.current = Date.now();

    const recognition = new SpeechRecognitionCtor();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-GB";

    recognition.onresult = (event) => {
      let interim = "";

      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];

        if (result.isFinal) {
          finalTranscriptRef.current += `${result[0].transcript} `;
        } else {
          interim += result[0].transcript;
        }
      }

      lastResultAtRef.current = Date.now();
      interimRef.current = interim;
      setInterimTranscript(interim);
    };

    recognition.onerror = (event) => {
      if (event.error === "no-speech") {
        // Expected when the mic is open but quiet. Our own timer handles
        // closing the session, so this is not surfaced to the user.
        return;
      }

      if (event.error === "aborted") return;

      if (event.error === "not-allowed") {
        setError("Microphone access was blocked. Enable it in your browser settings.");
      } else {
        setError(`Voice input failed: ${event.error}`);
      }

      stopListening();
    };

    // Chrome sometimes ends the session on its own despite `continuous`.
    // Restart it so our silence timer stays the single source of truth.
    recognition.onend = () => {
      if (!listeningRef.current) return;

      try {
        recognition.start();
      } catch {
        stopListening({ emit: true });
      }
    };

    try {
      recognition.start();
    } catch {
      setError("Could not start voice input.");
      return;
    }

    recognitionRef.current = recognition;
    listeningRef.current = true;
    setListening(true);

    silenceTimerRef.current = setInterval(() => {
      const elapsed = Date.now() - lastResultAtRef.current;

      if (elapsed >= SILENCE_THRESHOLD_MS) {
        stopListening({ emit: true });
      }
    }, SILENCE_CHECK_INTERVAL_MS);
  }, [stopListening]);

  useEffect(() => {
    return () => {
      clearSilenceTimer();

      if (recognitionRef.current) {
        recognitionRef.current.onend = null;

        try {
          recognitionRef.current.stop();
        } catch {
          // Ignore -- component is unmounting.
        }
      }
    };
  }, [clearSilenceTimer]);

  return {
    supported,
    listening,
    interimTranscript,
    error,
    startListening,
    stopListening,
  };
}