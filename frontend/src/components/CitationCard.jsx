function CitationCard({ citation, expanded = false }) {
  return (
    <div
      style={{
        marginTop: "8px",
        padding: "10px 12px",
        background: "#f8fafc",
        border: "1px solid #e5e7eb",
        borderRadius: "8px",
      }}
    >
      {/* Compact source row */}
      <div
        style={{
          fontSize: "14px",
          color: "#1f2937",
          fontWeight: 500,
          lineHeight: 1.5,
        }}
      >
        📄 <strong>{citation.filename}</strong>
        {" • "}
        Page {citation.page}
        {" • "}
        {citation.section}
      </div>

      {/* Supporting evidence (hidden by default) */}
      {expanded && (
        <div
          style={{
            marginTop: "10px",
            paddingTop: "10px",
            borderTop: "1px solid #e5e7eb",
            color: "#4b5563",
            fontSize: "13px",
            lineHeight: 1.6,
            fontStyle: "italic",
          }}
        >
          "{citation.snippet}..."
        </div>
      )}
    </div>
  );
}

export default CitationCard;