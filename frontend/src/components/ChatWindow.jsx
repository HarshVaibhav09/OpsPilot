import { useEffect, useRef, useState } from "react";

import { getChatHistory, sendMessage } from "../services/api";
import ChatInput from "./ChatInput";
import MessageBubble from "./MessageBubble";

function ChatWindow({
  sessionId,
  selectedDocument,
  developerMode,
}) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
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

  async function handleSend(message) {
    const userMessage = {
      role: "user",
      content: message,
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
        },
      ]);
    } catch (err) {
      setError(err.message || "Failed to generate response.");
    } finally {
      setLoading(false);
    }
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
        onSend={handleSend}
      />
    </div>
  );
}

export default ChatWindow;