import { useState } from "react";

import { synthesizeSpeech } from "../services/api";
import { unlockAudio, playAudioBlob } from "../services/audioPlayer";

function ChatInput({
  onSend,
  loading = false,
}) {
  const [message, setMessage] = useState("");

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

  // Temporary -- Phase 3 only. Verifies TTS playback in isolation before
  // speech recognition is wired in. Removed in Phase 5.
  async function handleTestSpeak() {
    unlockAudio();

    try {
      const blob = await synthesizeSpeech(
        "The vehicle damage cost is four thousand two hundred dollars."
      );

      await playAudioBlob(blob);
    } catch (error) {
      console.error("Speak failed:", error);
    }
  }

  return (
    <div
      style={{
        padding: "16px",
        background: "#ffffff",
        borderTop: "1px solid #e5e7eb",
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
        onClick={handleTestSpeak}
        style={{
          minWidth: "90px",
          height: "44px",
          border: "1px solid #d1d5db",
          borderRadius: "10px",
          background: "#ffffff",
          color: "#374151",
          fontWeight: "600",
          cursor: "pointer",
        }}
      >
        Test TTS
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
  );
}

export default ChatInput;