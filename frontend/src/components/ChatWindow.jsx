import { useEffect, useRef, useState } from "react";

import {
  getChatHistory,
  sendMessage,
  synthesizeSpeech,
} from "../services/api";
import { playAudioBlob, stopAudio } from "../services/audioPlayer";
import ChatInput from "./ChatInput";
import MessageBubble from "./MessageBubble";

function ChatWindow({
  sessionId,
  selectedDocument,
  developerMode,
}) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [error, setError] = useState("");

  const bottomRef = useRef(null);

  useEffect(() => {
    if (!sessionId) return;

    async function loadHistory() {
      try {
        const data = await getChatHistory(sessionId);

        setMessages(
          data.messages.map((message) => ({
            role: message.role,
            content: message.content,
            citations: [],
            confidence: null,
            documentAnalysis: [],
            developer: null,
            spoken: false,
          }))
        );
      } catch {
        setMessages([]);
      }
    }

    loadHistory();
  }, [sessionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({
      behavior: "smooth",
    });
  }, [messages, loading]);

  // Stop any audio still playing if the component unmounts mid-answer.
  useEffect(() => {
    return () => stopAudio();
  }, []);

  async function speakAnswer(answer) {
    setSpeaking(true);

    try {
      const blob = await synthesizeSpeech(answer);
      await playAudioBlob(blob);
    } catch (err) {
      // A failed spoken answer is not a failed answer -- the text is
      // already on screen, so this stays in the console rather than
      // surfacing as a chat error.
      console.error("Speech playback failed:", err);
    } finally {
      setSpeaking(false);
    }
  }

  async function handleSend(message, { spoken = false } = {}) {
    // A new turn always cancels the previous answer's audio.
    stopAudio();
    setSpeaking(false);

    const userMessage = {
      role: "user",
      content: message,
      spoken,
    };

    setMessages((prev) => [...prev, userMessage]);
    setLoading(true);
    setError("");

    try {
      const result = await sendMessage({
        session_id: sessionId,
        message,
        developer_mode: developerMode,
        hybrid_search: true,
        doc_id: selectedDocument,
      });

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: result.answer,
          confidence: result.confidence,
          citations: result.citations || [],
          documentAnalysis: result.document_analysis || [],
          developer: result.developer || null,
          spoken: false,
        },
      ]);

      setLoading(false);

      if (spoken && result.answer) {
        // Fire and forget -- the text is already rendering while the
        // audio is still being generated.
        speakAnswer(result.answer);
      }
    } catch (err) {
      setError(err.message || "Failed to generate response.");
      setLoading(false);
    }
  }

  function handleStopSpeaking() {
    stopAudio();
    setSpeaking(false);
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        background: "#f8fafc",
      }}
    >
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "24px",
        }}
      >
        {!messages.length && (
          <div
            style={{
              marginTop: "80px",
              textAlign: "center",
              color: "#6b7280",
            }}
          >
            <h3
              style={{
                marginBottom: "10px",
                color: "#1f2937",
              }}
            >
              Welcome to OpsPilot
            </h3>

            <p>
              Upload one or more PDF documents and start asking
              questions.
            </p>
          </div>
        )}

        {messages.map((message, index) => (
          <MessageBubble
            key={index}
            role={message.role}
            content={message.content}
            confidence={message.confidence}
            citations={message.citations}
            documentAnalysis={message.documentAnalysis}
            developer={message.developer}
            spoken={message.spoken}
          />
        ))}

        {loading && (
          <div
            style={{
              marginTop: "16px",
              color: "#2563eb",
              fontSize: "14px",
            }}
          >
            OpsPilot is thinking...
          </div>
        )}

        {speaking && (
          <div
            style={{
              marginTop: "16px",
              display: "flex",
              alignItems: "center",
              gap: "10px",
              color: "#2563eb",
              fontSize: "14px",
            }}
          >
            <span>Speaking...</span>

            <button
              onClick={handleStopSpeaking}
              style={{
                border: "1px solid #d1d5db",
                borderRadius: "8px",
                background: "#ffffff",
                color: "#374151",
                fontSize: "12px",
                padding: "4px 10px",
                cursor: "pointer",
              }}
            >
              Stop
            </button>
          </div>
        )}

        {!!error && (
          <div
            style={{
              marginTop: "16px",
              color: "#dc2626",
              fontSize: "14px",
            }}
          >
            {error}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <ChatInput
        loading={loading}
        speaking={speaking}
        onSend={handleSend}
      />
    </div>
  );
}

export default ChatWindow;