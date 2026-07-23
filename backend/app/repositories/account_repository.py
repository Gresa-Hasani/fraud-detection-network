"""Account node lookup, listing, and transaction history."""

from __future__ import annotations

from typing import Any

from app.core.database import Neo4jConnection


class AccountRepository:
    def __init__(self, connection: Neo4jConnection) -> None:
        self._db = connection

    def list_accounts(
        self, risk_level: str | None, status: str | None, limit: int, offset: int
    ) -> list[dict[str, Any]]:
        return self._db.run_query(
            """
            MATCH (a:Account)
            WHERE ($risk_level IS NULL OR a.risk_level = $risk_level)
              AND ($status IS NULL OR a.status = $status)
            RETURN a
            ORDER BY a.risk_score DESC, a.account_id
            SKIP $offset
            LIMIT $limit
            """,
            {"risk_level": risk_level, "status": status, "limit": limit, "offset": offset},
        )

    def count_accounts(self, risk_level: str | None, status: str | None) -> int:
        result = self._db.run_query(
            """
            MATCH (a:Account)
            WHERE ($risk_level IS NULL OR a.risk_level = $risk_level)
              AND ($status IS NULL OR a.status = $status)
            RETURN count(a) AS n
            """,
            {"risk_level": risk_level, "status": status},
        )
        return result[0]["n"]

    def get_account(self, account_id: str) -> dict[str, Any] | None:
        result = self._db.run_query("MATCH (a:Account {account_id: $account_id}) RETURN a", {"account_id": account_id})
        return result[0]["a"] if result else None

    def get_account_owner(self, account_id: str) -> dict[str, Any] | None:
        result = self._db.run_query(
            "MATCH (c:Customer)-[:OWNS]->(a:Account {account_id: $account_id}) RETURN c",
            {"account_id": account_id},
        )
        return result[0]["c"] if result else None

    def get_account_transactions(self, account_id: str, limit: int, offset: int) -> list[dict[str, Any]]:
        return self._db.run_query(
            """
            MATCH (a:Account {account_id: $account_id})<-[:FROM_ACCOUNT|TO_ACCOUNT]-(t:Transaction)
            RETURN DISTINCT t
            ORDER BY t.timestamp DESC
            SKIP $offset
            LIMIT $limit
            """,
            {"account_id": account_id, "limit": limit, "offset": offset},
        )

    def get_account_devices(self, account_id: str) -> list[dict[str, Any]]:
        return self._db.run_query(
            """
            MATCH (c:Customer)-[:OWNS]->(:Account {account_id: $account_id})
            MATCH (c)-[:USES_DEVICE]->(d:Device)
            RETURN DISTINCT d
            """,
            {"account_id": account_id},
        )

    def get_account_ips(self, account_id: str) -> list[dict[str, Any]]:
        return self._db.run_query(
            """
            MATCH (a:Account {account_id: $account_id})<-[:FROM_ACCOUNT]-(t:Transaction)
            MATCH (t)-[:ORIGINATED_FROM]->(ip:IPAddress)
            RETURN DISTINCT ip
            """,
            {"account_id": account_id},
        )
