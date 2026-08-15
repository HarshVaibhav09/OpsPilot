import { useCallback, useState } from "react";

import { useSpeechRecognition } from "../hooks/useSpeechRecognition";
import { unlockAudio } from "../services/audioPlayer";

function MicIcon({ size = 20 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="9" y="2" width="6" height="11" rx="3" />
      <path d="M5 10v1a7 7 0 0 0 14 0v-1" />
      <line x1="12" y1="18" x2="12" y2="22" />
    </svg>
  );
}

function ChatInput({
  onSend,
  loading = false,
}) {
  const [message, setMessage] = useState("");

  // Phase 4 only -- proves recognition works before it is wired to chat.
  const [lastTranscript, setLastTranscript] = useState("");

  const handleTranscript = useCallback((transcript) => {
    setLastTranscript(transcript);
  }, []);

  const {
    supported,
    listening,
    interimTranscript,
    error,
    startListening,
    stopListening,
  } = useSpeechRecognition({ onResult: handleTranscript });

  async function handleSend() {
    const text = message.trim();

    if (!text || loading) return;

    setMessage("");

    await onSend(text);
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function handleMicClick() {
    // Arm the audio element while we still have a user gesture, so
    // playback is permitted later in the turn.
    unlockAudio();

    if (listening) {
      stopListening({ emit: true });
    } else {
      setLastTranscript("");
      startListening();
    }
  }

  return (
    <div
      style={{
        background: "#ffffff",
        borderTop: "1px solid #e5e7eb",
      }}
    >
      {(listening || lastTranscript || error) && (
        <div
          style={{
            padding: "10px 16px",
            borderBottom: "1px solid #f3f4f6",
            fontSize: "13px",
            color: error ? "#b91c1c" : "#6b7280",
            minHeight: "20px",
          }}
        >
          {error && <span>{error}</span>}

          {!error && listening && (
            <span>
              <strong style={{ color: "#dc2626" }}>Listening</strong>
              {interimTranscript && ` — ${interimTranscript}`}
            </span>
          )}

          {!error && !listening && lastTranscript && (
            <span>
              <strong>Captured:</strong> {lastTranscript}
            </span>
          )}
        </div>
      )}

      <div
        style={{
          padding: "16px",
          display: "flex",
          gap: "12px",
          alignItems: "flex-end",
        }}
      >
        <textarea
          value={message}
          rows={2}
          disabled={loading}
          placeholder="Ask about your uploaded documents..."
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          style={{
            flex: 1,
            resize: "none",
            padding: "12px",
            borderRadius: "10px",
            border: "1px solid #d1d5db",
            fontSize: "14px",
            lineHeight: "1.5",
            outline: "none",
          }}
        />

        <button
          onClick={handleMicClick}
          disabled={!supported}
          title={
            supported
              ? "Speak your question"
              : "Voice input needs Chrome or Edge"
          }
          style={{
            width: "44px",
            height: "44px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            border: listening ? "none" : "1px solid #d1d5db",
            borderRadius: "50%",
            background: listening ? "#dc2626" : "#ffffff",
            color: listening ? "#ffffff" : "#374151",
            cursor: supported ? "pointer" : "not-allowed",
            opacity: supported ? 1 : 0.5,
            transition: "background 0.15s ease, color 0.15s ease",
            animation: listening
              ? "opspilot-mic-pulse 1.4s ease-in-out infinite"
              : "none",
          }}
        >
          <MicIcon />
        </button>

        <button
          onClick={handleSend}
          disabled={loading || !message.trim()}
          style={{
            minWidth: "110px",
            height: "44px",
            border: "none",
            borderRadius: "10px",
            background: loading ? "#93c5fd" : "#2563eb",
            color: "#ffffff",
            fontWeight: "600",
            cursor:
              loading || !message.trim()
                ? "not-allowed"
                : "pointer",
          }}
        >
          {loading ? "Thinking..." : "Send"}
        </button>
      </div>
    </div>
  );
}

export default ChatInput;