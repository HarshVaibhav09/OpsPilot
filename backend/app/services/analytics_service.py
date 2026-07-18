from collections import Counter
from datetime import datetime


class AnalyticsService:
    def __init__(self):
        self.logs = []

    def log_query(
        self,
        session_id: str,
        query: str,
        retrieved: int,
        confidence: float,
    ):
        self.logs.append(
            {
                "timestamp": datetime.utcnow(),
                "session_id": session_id,
                "query": query,
                "retrieved": retrieved,
                "confidence": confidence,
            }
        )

    def get_summary(self) -> dict:

        if not self.logs:
            return {
                "total_queries": 0,
                "average_confidence": 0.0,
                "average_chunks_retrieved": 0.0,
                "top_queries": [],
            }

        total = len(self.logs)

        return {
            "total_queries": total,
            "average_confidence": round(
                sum(log["confidence"] for log in self.logs) / total,
                2,
            ),
            "average_chunks_retrieved": round(
                sum(log["retrieved"] for log in self.logs) / total,
                2,
            ),
            "top_queries": Counter(
                log["query"] for log in self.logs
            ).most_common(10),
        }


analytics_service = AnalyticsService()