import { useEffect, useRef, useState } from "react";

import { getUploadStatus, uploadDocuments } from "../services/api";

const POLL_INTERVAL_MS = 2000;

function Uploader({ onUploadComplete, onActiveCountChange }) {
  const inputRef = useRef(null);
  const pollRef = useRef(null);

  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [fileStatuses, setFileStatuses] = useState([]);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  async function upload(files) {
    if (!files.length) return;

    setUploading(true);
    setError("");
    setFileStatuses([]);

    try {
      const job = await uploadDocuments(files);

      if (job.rejected_files?.length) {
        setError(job.rejected_files.join(" "));
      }

      if (!job.accepted_files?.length) {
        setUploading(false);
        return;
      }

      setFileStatuses(
        job.accepted_files.map((filename) => ({
          filename,
          status: "pending",
        }))
      );

      onActiveCountChange?.(job.accepted_files.length);

      pollJobStatus(job.job_id);
    } catch (err) {
      setError(err.message || "Upload failed.");
      setUploading(false);
      onActiveCountChange?.(0);
    } finally {
      if (inputRef.current) {
        inputRef.current.value = "";
      }
    }
  }

  function pollJobStatus(jobId) {
    pollRef.current = setInterval(async () => {
      try {
        const data = await getUploadStatus(jobId);
        setFileStatuses(data.files);

        const active = data.files.filter(
          (f) => f.status === "pending" || f.status === "processing"
        ).length;
        onActiveCountChange?.(active);

        if (data.status === "completed") {
          clearInterval(pollRef.current);
          setUploading(false);
          onActiveCountChange?.(0);
          onUploadComplete();
        }
      } catch (err) {
        clearInterval(pollRef.current);
        setUploading(false);
        onActiveCountChange?.(0);
        setError(err.message || "Lost track of upload progress.");
      }
    }, POLL_INTERVAL_MS);
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
          border: dragging ? "2px solid #2563eb" : "2px dashed #cbd5e1",
          borderRadius: "10px",
          padding: "22px",
          textAlign: "center",
          cursor: "pointer",
          background: dragging ? "#eff6ff" : "#ffffff",
          transition: "0.2s",
        }}
      >
        <div style={{ fontSize: "15px", fontWeight: 600, color: "#1f2937" }}>
          📄 Upload PDF Documents
        </div>

        <div style={{ marginTop: "8px", fontSize: "13px", color: "#6b7280" }}>
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
          onChange={(e) => upload(Array.from(e.target.files || []))}
        />
      </div>

      {fileStatuses.length > 0 && (
        <div style={{ marginTop: "12px" }}>
          <div
            style={{
              height: "6px",
              background: "#e5e7eb",
              borderRadius: "999px",
              overflow: "hidden",
              marginBottom: "10px",
            }}
          >
            <div
              style={{
                height: "100%",
                width: `${calculateProgress(fileStatuses)}%`,
                background: "#2563eb",
                transition: "width 0.3s ease",
              }}
            />
          </div>

          {fileStatuses.map((f) => (
            <div key={f.filename} style={{ marginBottom: "4px" }}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  fontSize: "13px",
                  padding: "6px 0",
                  color: f.status === "failed" ? "#dc2626" : "#374151",
                }}
              >
                <span>{f.filename}</span>
                <span>{statusLabel(f.status)}</span>
              </div>

              {f.status === "failed" && f.error && (
                <div
                  style={{
                    fontSize: "12px",
                    color: "#b91c1c",
                    background: "#fef2f2",
                    border: "1px solid #fecaca",
                    borderRadius: "6px",
                    padding: "6px 8px",
                    marginBottom: "6px",
                  }}
                >
                  {f.error}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {!!error && (
        <p style={{ marginTop: "12px", fontSize: "13px", color: "#dc2626" }}>
          {error}
        </p>
      )}
    </>
  );
}

function calculateProgress(fileStatuses) {
  if (!fileStatuses.length) return 0;
  const done = fileStatuses.filter(
    (f) => f.status === "completed" || f.status === "failed"
  ).length;
  return Math.round((done / fileStatuses.length) * 100);
}

function statusLabel(status) {
  switch (status) {
    case "pending":
      return "⏳ Queued";
    case "processing":
      return "⚙️ Processing...";
    case "completed":
      return "✅ Done";
    case "failed":
      return "❌ Failed";
    default:
      return status;
  }
}

export default Uploader;