from app.db.session_store import session_store


def get_recent_history(
    session_id: str,
    limit: int = 6,
) -> list[dict]:
    return session_store.get_history(
        session_id=session_id,
        limit=limit,
    )


def save_turn(
    session_id: str,
    user_message: str,
    assistant_message: str,
    standalone_query: str | None = None,
    confidence: float = 0.0,
    latency: float = 0.0,
):
    if user_message.strip():
        session_store.add_message(
            session_id=session_id,
            role="user",
            content=user_message.strip(),
            standalone_query=standalone_query,
            confidence=confidence,
            latency=latency,
        )

    if assistant_message.strip():
        session_store.add_message(
            session_id=session_id,
            role="assistant",
            content=assistant_message.strip(),
            confidence=confidence,
            latency=latency,
        )