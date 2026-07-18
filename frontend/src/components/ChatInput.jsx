import { useState } from "react";

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