import { useEffect, useState } from "react";

import { createSession } from "./services/api";
import ChatWindow from "./components/ChatWindow";
import DocumentSidebar from "./components/DocumentSidebar";
import Header from "./components/Header";

function App() {
  const [sessionId, setSessionId] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [developerMode, setDeveloperMode] = useState(false);
  const [refreshDocuments, setRefreshDocuments] = useState(0);

  useEffect(() => {
    async function initialize() {
      try {
        const session = await createSession();
        setSessionId(session.session_id);
      } catch (err) {
        console.error("Failed to create session:", err);
      }
    }

    initialize();
  }, []);

  function handleDocumentsUpdated() {
    setRefreshDocuments((prev) => prev + 1);
  }

  return (
    <div
      style={{
        height: "100vh",
        display: "flex",
        flexDirection: "column",
        background: "#f8fafc",
      }}
    >
      <Header
        developerMode={developerMode}
        onToggleDeveloper={() => setDeveloperMode((prev) => !prev)}
        documentCount={documents.length}
      />

      <div
        style={{
          flex: 1,
          display: "flex",
          overflow: "hidden",
        }}
      >
        <DocumentSidebar
          documents={documents}
          setDocuments={setDocuments}
          selectedDocument={selectedDocument}
          onSelectDocument={setSelectedDocument}
          refreshTrigger={refreshDocuments}
          onDocumentsChanged={handleDocumentsUpdated}
        />

        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
          }}
        >
          {sessionId ? (
            <ChatWindow
              sessionId={sessionId}
              selectedDocument={selectedDocument}
              developerMode={developerMode}
            />
          ) : (
            <div
              style={{
                margin: "auto",
                fontSize: "18px",
                color: "#666",
              }}
            >
              Starting OpsPilot...
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;