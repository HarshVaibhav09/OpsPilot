import { useState } from "react";
import ReactMarkdown from "react-markdown";

import CitationCard from "./CitationCard";
import DeveloperPanel from "./DeveloperPanel";
import DocumentAnalysisCard from "./DocumentAnalysisCard";

function SpokenTag() {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "5px",
        marginBottom: "6px",
        fontSize: "11px",
        letterSpacing: "0.03em",
        textTransform: "uppercase",
        color: "rgba(255,255,255,0.75)",
      }}
    >
      <svg
        width="11"
        height="11"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <rect x="9" y="2" width="6" height="11" rx="3" />
        <path d="M5 10v1a7 7 0 0 0 14 0v-1" />
        <line x1="12" y1="18" x2="12" y2="22" />
      </svg>

      <span>Spoken</span>
    </div>
  );
}

function MessageBubble({
  role,
  content,
  confidence = null,
  citations = [],
  documentAnalysis = [],
  developer = null,
  spoken = false,
}) {
  const isUser = role === "user";
  const [showEvidence, setShowEvidence] = useState(false);

  return (
    <div
      style={{
        display: "flex",
        justifyContent: isUser ? "flex-end" : "flex-start",
        marginBottom: "18px",
      }}
    >
      <div
        style={{
          maxWidth: "78%",
          padding: "16px",
          borderRadius: "12px",
          background: isUser ? "#2563eb" : "#ffffff",
          color: isUser ? "#ffffff" : "#111827",
          border: isUser ? "none" : "1px solid #e5e7eb",
          boxShadow: isUser
            ? "none"
            : "0 1px 3px rgba(0,0,0,0.06)",
        }}
      >
        {isUser ? (
          <div>
            {spoken && <SpokenTag />}

            <div
              style={{
                whiteSpace: "pre-wrap",
                lineHeight: 1.6,
              }}
            >
              {content}
            </div>
          </div>
        ) : (
          <>
            <div
              className="markdown-body"
              style={{
                lineHeight: 1.7,
              }}
            >
              <ReactMarkdown>{content}</ReactMarkdown>
            </div>

            {confidence !== null && (
              <div
                style={{
                  marginTop: "14px",
                  fontSize: "13px",
                  color: "#2563eb",
                  fontWeight: 600,
                }}
              >
                Confidence: {(confidence * 100).toFixed(0)}%
              </div>
            )}

            {citations.length > 0 && (
                <div style={{ marginTop: "18px" }}>
                  <h4
                    style={{
                      marginBottom: "10px",
                      color: "#1f2937",
                    }}
                  >
                    Sources ({citations.length})
                  </h4>

                  {citations.map((citation, index) => (
                    <CitationCard
                      key={index}
                      citation={citation}
                      expanded={showEvidence}
                    />
                  ))}

                  <button
                    onClick={() => setShowEvidence(!showEvidence)}
                    style={{
                      marginTop: "12px",
                      border: "none",
                      background: "transparent",
                      color: "#2563eb",
                      cursor: "pointer",
                      fontSize: "13px",
                      fontWeight: 600,
                      padding: 0,
                    }}
                  >
                    {showEvidence
                      ? "Hide Supporting Evidence"
                      : "Show Supporting Evidence"}
                  </button>
                </div>
            )}

            {documentAnalysis.map((analysis, index) => (
              <DocumentAnalysisCard
                key={index}
                analysis={analysis}
              />
            ))}

            {developer && (
              <DeveloperPanel
                developer={developer}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default MessageBubble;