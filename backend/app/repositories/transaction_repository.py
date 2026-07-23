"""Transaction node lookup and filtered listing."""

from __future__ import annotations

from typing import Any

from app.core.database import Neo4jConnection


class TransactionRepository:
    def __init__(self, connection: Neo4jConnection) -> None:
        self._db = connection

    def list_transactions(
        self,
        transaction_type: str | None,
        min_amount: float | None,
        start: str | None,
        end: str | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        return self._db.run_query(
            """
            MATCH (t:Transaction)
            WHERE ($transaction_type IS NULL OR t.transaction_type = $transaction_type)
              AND ($min_amount IS NULL OR t.amount >= $min_amount)
              AND ($start IS NULL OR t.timestamp >= datetime($start))
              AND ($end IS NULL OR t.timestamp <= datetime($end))
            RETURN t
            ORDER BY t.timestamp DESC
            SKIP $offset
            LIMIT $limit
            """,
            {
                "transaction_type": transaction_type,
                "min_amount": min_amount,
                "start": start,
                "end": end,
                "limit": limit,
                "offset": offset,
            },
        )

    def get_transaction(self, transaction_id: str) -> dict[str, Any] | None:
        result = self._db.run_query(
            "MATCH (t:Transaction {transaction_id: $transaction_id}) RETURN t",
            {"transaction_id": transaction_id},
        )
        return result[0]["t"] if result else None

    def list_flagged(self, limit: int, offset: int) -> list[dict[str, Any]]:
        return self._db.run_query(
            """
            MATCH (t:Transaction {is_flagged: true})
            RETURN t
            ORDER BY t.timestamp DESC
            SKIP $offset
            LIMIT $limit
            """,
            {"limit": limit, "offset": offset},
        )

    def list_high_risk(self, min_risk_score: int, limit: int, offset: int) -> list[dict[str, Any]]:
        return self._db.run_query(
            """
            MATCH (t:Transaction)
            WHERE t.risk_score >= $min_risk_score
            RETURN t
            ORDER BY t.risk_score DESC
            SKIP $offset
            LIMIT $limit
            """,
            {"min_risk_score": min_risk_score, "limit": limit, "offset": offset},
        )
