import sqlite3
from datetime import datetime

from app.core.config import settings


class SessionStore:
    def __init__(self):
        self.db_path = settings.session_db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    standalone_query TEXT,
                    confidence REAL DEFAULT 0,
                    latency REAL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
            """)

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        standalone_query: str | None = None,
        confidence: float = 0.0,
        latency: float = 0.0,
    ):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO messages (
                    session_id,
                    role,
                    content,
                    standalone_query,
                    confidence,
                    latency,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    role,
                    content,
                    standalone_query,
                    confidence,
                    latency,
                    datetime.utcnow().isoformat(),
                ),
            )

    def get_history(
        self,
        session_id: str,
        limit: int = 12,
    ) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT role, content, standalone_query
                FROM messages
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()

        return [
            {
                "role": role,
                "content": content,
                "standalone_query": standalone_query,
            }
            for role, content, standalone_query in reversed(rows)
        ]

    def clear_session(self, session_id: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM messages WHERE session_id = ?",
                (session_id,),
            )


session_store = SessionStore()