function DeveloperPanel({ developer }) {
  if (!developer) return null;

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
          margin: "0 0 16px",
          color: "#1f2937",
        }}
      >
        🛠 Developer Mode
      </h4>

      <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))",
              gap: "12px",
              marginBottom: "18px",
            }}
          >
            <Metric
              label="Average Similarity"
              value={`${(developer.avg_similarity * 100).toFixed(1)}%`}
            />

            <Metric
              label="Retrieved Chunks"
              value={developer.retrieved_chunks.length}
            />

            <Metric
              label="Context Length"
              value={`${developer.context_length.toLocaleString()} chars`}
            />

            <Metric
              label="Hybrid Search"
              value={developer.hybrid_search ? "Enabled" : "Disabled"}
            />
      </div>

      <div style={{ marginBottom: "18px" }}>
        <div
          style={{
            fontWeight: 600,
            marginBottom: "8px",
          }}
        >
          Rewritten Query
        </div>

        <div
          style={{
            background: "#f8fafc",
            border: "1px solid #e5e7eb",
            borderRadius: "8px",
            padding: "12px",
            fontSize: "14px",
            color: "#374151",
            lineHeight: 1.6,
          }}
        >
          {developer.rewritten_query}
        </div>
      </div>

      <div>
        <div
          style={{
            fontWeight: 600,
            marginBottom: "10px",
          }}
        >
          Retrieved Chunks
        </div>

        {developer.retrieved_chunks.map((chunk, index) => (
          <div
            key={index}
            style={{
              marginBottom: "12px",
              padding: "12px",
              background: "#f8fafc",
              border: "1px solid #e5e7eb",
              borderRadius: "8px",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                marginBottom: "8px",
                fontSize: "13px",
              }}
            >
              <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: "10px",
                  }}
                >
                  <strong style={{ color: "#1f2937" }}>
                    📄 {chunk.filename}
                  </strong>

                  <span
                    style={{
                      fontSize: "12px",
                      color: "#6b7280",
                    }}
                  >
                    Page {chunk.page}
                  </span>
              </div>
            </div>

            <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: "14px",
                  marginBottom: "10px",
                  fontSize: "12px",
                  color: "#6b7280",
                }}
              >
                <span>
                  Similarity: {(chunk.similarity * 100).toFixed(1)}%
                </span>

                <span>
                  Section: {chunk.section}
                </span>

                <span>
                  Type: {contentTypeLabel(chunk.content_type)}
                </span>

                <span>
                  Doc type: {chunk.document_type || "general"}
                </span>
            </div>

            <div
              style={{
                fontSize: "13px",
                color: "#374151",
                lineHeight: 1.5,
              }}
            >
              {chunk.text.length > 220
                ? `${chunk.text.slice(0, 220)}...`
                : chunk.text}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function contentTypeLabel(contentType) {
  switch (contentType) {
    case "table":
      return "Table";
    case "data_log_row":
      return "Data Log Row";
    default:
      return "Text";
  }
}

function Metric({ label, value }) {
  return (
    <div
      style={{
        background: "#f8fafc",
        border: "1px solid #e5e7eb",
        borderRadius: "8px",
        padding: "12px",
      }}
    >
      <div
        style={{
          fontSize: "12px",
          color: "#6b7280",
          marginBottom: "4px",
        }}
      >
        {label}
      </div>

      <div
        style={{
          fontSize: "18px",
          fontWeight: "600",
          color: "#2563eb",
        }}
      >
        {value}
      </div>
    </div>
  );
}

export default DeveloperPanel;