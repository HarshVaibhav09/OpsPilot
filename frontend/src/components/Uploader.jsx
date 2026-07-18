import { useRef, useState } from "react";

import { uploadDocuments } from "../services/api";

function Uploader({ onUploadComplete }) {
  const inputRef = useRef(null);

  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");

  async function upload(files) {
    if (!files.length) return;

    setUploading(true);
    setError("");

    try {
      await uploadDocuments(files);
      onUploadComplete();
    } catch (err) {
      setError(err.message || "Upload failed.");
    } finally {
      setUploading(false);

      if (inputRef.current) {
        inputRef.current.value = "";
      }
    }
  }

  function handleDrop(e) {
    e.preventDefault();
    setDragging(false);

    upload(
      Array.from(e.dataTransfer.files).filter((file) =>
        file.name.toLowerCase().endsWith(".pdf")
      )
    );
  }

  return (
    <>
      <div
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        style={{
          border: dragging
            ? "2px solid #2563eb"
            : "2px dashed #cbd5e1",
          borderRadius: "10px",
          padding: "22px",
          textAlign: "center",
          cursor: "pointer",
          background: dragging ? "#eff6ff" : "#ffffff",
          transition: "0.2s",
        }}
      >
        <div
          style={{
            fontSize: "15px",
            fontWeight: 600,
            color: "#1f2937",
          }}
        >
          📄 Upload PDF Documents
        </div>

        <div
          style={{
            marginTop: "8px",
            fontSize: "13px",
            color: "#6b7280",
          }}
        >
          Drag & drop PDFs here
          <br />
          or click to browse
        </div>

        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf"
          hidden
          disabled={uploading}
          onChange={(e) =>
            upload(Array.from(e.target.files || []))
          }
        />
      </div>

      {uploading && (
        <p
          style={{
            marginTop: "12px",
            fontSize: "13px",
            color: "#2563eb",
          }}
        >
          Uploading and indexing documents...
        </p>
      )}

      {!!error && (
        <p
          style={{
            marginTop: "12px",
            fontSize: "13px",
            color: "#dc2626",
          }}
        >
          {error}
        </p>
      )}
    </>
  );
}

export default Uploader;