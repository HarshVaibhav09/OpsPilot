const BASE_URL = import.meta.env.VITE_API_URL;

async function request(endpoint, options = {}) {
  const response = await fetch(`${BASE_URL}${endpoint}`, options);

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      data.detail || `Request failed (${response.status})`
    );
  }

  return data;
}

export async function uploadDocuments(files) {
  const formData = new FormData();

  files.forEach((file) =>
    formData.append("files", file)
  );

  return request("/documents/upload", {
    method: "POST",
    body: formData,
  });
}

export function getUploadStatus(jobId) {
  return request(`/documents/upload/${jobId}/status`);
}

export function listDocuments() {
  return request("/documents");
}

export function deleteDocument(docId) {
  return request(`/documents/${docId}`, {
    method: "DELETE",
  });
}

export function createSession() {
  return request("/chat/new", {
    method: "POST",
  });
}

export function sendMessage(payload) {
  return request("/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export function getChatHistory(sessionId) {
  return request(`/chat/${sessionId}/history`);
}

async function requestBlob(endpoint, options = {}) {
  const response = await fetch(`${BASE_URL}${endpoint}`, options);

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));

    throw new Error(
      data.detail || `Request failed (${response.status})`
    );
  }

  return response.blob();
}

export async function synthesizeSpeech(text) {
  const response = await fetch(`${BASE_URL}/voice/speak`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ text }),
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const detail = data.detail || {};

    const error = new Error(
      detail.message || `Speech request failed (${response.status})`
    );

    // Carries the cleaned text so the caller can speak it locally.
    error.spokenText = detail.spoken_text || "";

    throw error;
  }

  return response.blob();
}