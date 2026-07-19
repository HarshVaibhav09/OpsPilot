import { useEffect, useState } from "react";

import { deleteDocument, listDocuments } from "../services/api";
import Uploader from "./Uploader";

function DocumentSidebar({
  documents,
  setDocuments,
  selectedDocument,
  onSelectDocument,
  refreshTrigger,
  onDocumentsChanged,
}) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [uploadingCount, setUploadingCount] = useState(0);

  useEffect(() => {
    fetchDocuments();
  }, [refreshTrigger]);

  async function fetchDocuments() {
    setLoading(true);
    setError("");

    try {
      const data = await listDocuments();
      setDocuments(data.documents);
    } catch (err) {
      setError(err.message || "Failed to load documents.");
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(docId) {
    try {
      await deleteDocument(docId);

      if (selectedDocument === docId) {
        onSelectDocument(null);
      }

      onDocumentsChanged();
    } catch (err) {
      setError(err.message || "Unable to delete document.");
    }
  }

  return (
    <aside
      style={{
        width: "330px",
        background: "#ffffff",
        borderRight: "1px solid #e5e7eb",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          padding: "20px",
          borderBottom: "1px solid #e5e7eb",
        }}
      >
        <Uploader
          onUploadComplete={onDocumentsChanged}
          onActiveCountChange={setUploadingCount}
        />
      </div>

      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "16px",
        }}
      >
        {uploadingCount > 0 && (
          <p style={{ color: "#2563eb", fontSize: "13px", marginBottom: "12px" }}>
            ⚙️ {uploadingCount} document{uploadingCount > 1 ? "s" : ""} still processing...
          </p>
        )}

        {loading && (
          <p style={{ color: "#6b7280" }}>
            Loading documents...
          </p>
        )}

        {error && (
          <p style={{ color: "#dc2626" }}>
            {error}
          </p>
        )}

        {!loading && !documents.length && !uploadingCount && (
          <p
            style={{
              color: "#6b7280",
              fontSize: "14px",
            }}
          >
            Upload one or more PDFs to begin.
          </p>
        )}

        {documents.map((doc) => {
          const selected = selectedDocument === doc.doc_id;

          return (
            <div
              key={doc.doc_id}
              onClick={() =>
                onSelectDocument(
                  selected ? null : doc.doc_id
                )
              }
              style={{
                border: selected
                  ? "2px solid #2563eb"
                  : "1px solid #e5e7eb",
                borderRadius: "10px",
                padding: "14px",
                marginBottom: "14px",
                cursor: "pointer",
                background: selected
                  ? "#eff6ff"
                  : "#ffffff",
              }}
            >
              <div
                style={{
                  fontWeight: 600,
                  color: "#1f2937",
                }}
              >
                📄 {doc.filename}
              </div>

              <div
                style={{
                  marginTop: "6px",
                  color: "#6b7280",
                  fontSize: "13px",
                }}
              >
                {doc.page_count} pages • {doc.chunk_count} chunks
              </div>

              <div
                style={{
                  marginTop: "12px",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <span
                  style={{
                    fontSize: "12px",
                    color: doc.has_conflicts
                      ? "#dc2626"
                      : "#16a34a",
                  }}
                >
                  {doc.has_conflicts
                    ? "⚠ Contradictions"
                    : "✓ No Contradictions"}
                </span>

                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(doc.doc_id);
                  }}
                  style={{
                    border: "none",
                    background: "transparent",
                    color: "#dc2626",
                    cursor: "pointer",
                    fontSize: "12px",
                  }}
                >
                  Delete
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </aside>
  );
}

export default DocumentSidebar;