function Header({
  documentCount,
  developerMode,
  onToggleDeveloper,
}) {
  return (
    <header
      style={{
        height: "64px",
        padding: "0 24px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        background: "#ffffff",
        borderBottom: "1px solid #e5e7eb",
        flexShrink: 0,
      }}
    >
      <div>
        <h2
          style={{
            margin: 0,
            fontSize: "22px",
            fontWeight: "700",
            color: "#1f2937",
          }}
        >
          OpsPilot
        </h2>

        <p
          style={{
            margin: "4px 0 0",
            fontSize: "13px",
            color: "#6b7280",
          }}
        >
          Enterprise Document Intelligence
        </p>
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "24px",
        }}
      >
        <div
          style={{
            textAlign: "right",
          }}
        >
          <div
            style={{
              fontSize: "13px",
              color: "#6b7280",
            }}
          >
            Documents Loaded
          </div>

          <div
            style={{
              fontSize: "18px",
              fontWeight: "600",
              color: "#2563eb",
            }}
          >
            {documentCount}
          </div>
        </div>

        <label
          style={{
            display: "flex",
            alignItems: "center",
            gap: "10px",
            cursor: "pointer",
            userSelect: "none",
            fontSize: "14px",
            color: "#374151",
          }}
        >
          <input
            type="checkbox"
            checked={developerMode}
            onChange={onToggleDeveloper}
          />

          Developer Mode
        </label>
      </div>
    </header>
  );
}

export default Header;