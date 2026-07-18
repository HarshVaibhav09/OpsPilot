function DocumentAnalysisCard({ analysis }) {
  if (!analysis) return null;

  return (
    <div
      style={{
        marginTop: "14px",
        padding: "16px",
        background: "#ffffff",
        border: "1px solid #e5e7eb",
        borderRadius: "10px",
      }}
    >
      <h4
        style={{
          margin: "0 0 14px",
          color: "#1f2937",
        }}
      >
        📑 Document Analysis
      </h4>


      <div style={{ marginBottom: "18px" }}>
        <div
          style={{
            fontWeight: 600,
            marginBottom: "8px",
          }}
        >
          Contradictions
        </div>

        {analysis.contradictions?.has_conflict ? (
          <div>
            {analysis.contradictions.conflicts.map((conflict, index) => (
              <div
                key={index}
                style={{
                  marginBottom: "12px",
                  padding: "10px",
                  background: "#fef2f2",
                  border: "1px solid #fecaca",
                  borderRadius: "8px",
                }}
              >
                <div
                  style={{
                    fontWeight: 600,
                    color: "#b91c1c",
                  }}
                >
                  {conflict.topic}
                </div>

                <div
                  style={{
                    marginTop: "6px",
                    fontSize: "13px",
                    color: "#374151",
                  }}
                >
                  <strong>Page {conflict.page_a}:</strong>{" "}
                  {conflict.statement_a}
                </div>

                <div
                  style={{
                    marginTop: "6px",
                    fontSize: "13px",
                    color: "#374151",
                  }}
                >
                  <strong>Page {conflict.page_b}:</strong>{" "}
                  {conflict.statement_b}
                </div>

                <div
                  style={{
                    marginTop: "8px",
                    fontSize: "12px",
                    color: "#dc2626",
                  }}
                >
                  Severity: {conflict.severity}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div
            style={{
              color: "#16a34a",
              fontSize: "14px",
            }}
          >
            ✓ No contradictions detected.
          </div>
        )}
      </div>

      {!!analysis.query_suggestions?.length && (
        <div>
          <div
            style={{
              fontWeight: 600,
              marginBottom: "8px",
            }}
          >
            Suggested Questions
          </div>

          <ul
            style={{
              margin: 0,
              paddingLeft: "18px",
              color: "#374151",
            }}
          >
            {analysis.query_suggestions.map((question) => (
              <li
                key={question}
                style={{
                  marginBottom: "6px",
                  fontSize: "14px",
                }}
              >
                {question}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default DocumentAnalysisCard;