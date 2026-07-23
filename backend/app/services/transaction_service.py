from __future__ import annotations

from typing import Any

from app.core.database import Neo4jConnection
from app.core.exceptions import EntityNotFoundError, InvalidDateRangeError
from app.repositories.transaction_repository import TransactionRepository


class TransactionService:
    def __init__(self, connection: Neo4jConnection) -> None:
        self._repo = TransactionRepository(connection)

    def list_transactions(
        self,
        transaction_type: str | None,
        min_amount: float | None,
        start: str | None,
        end: str | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        if start and end and start > end:
            raise InvalidDateRangeError("start must be before end.", {"start": start, "end": end})
        rows = self._repo.list_transactions(transaction_type, min_amount, start, end, limit, offset)
        return [row["t"] for row in rows]

    def get_transaction(self, transaction_id: str) -> dict[str, Any]:
        transaction = self._repo.get_transaction(transaction_id)
        if transaction is None:
            raise EntityNotFoundError(f"Transaction {transaction_id} was not found.")
        return transaction

    def list_flagged(self, limit: int, offset: int) -> list[dict[str, Any]]:
        return [row["t"] for row in self._repo.list_flagged(limit, offset)]

    def list_high_risk(self, min_risk_score: int, limit: int, offset: int) -> list[dict[str, Any]]:
        return [row["t"] for row in self._repo.list_high_risk(min_risk_score, limit, offset)]
