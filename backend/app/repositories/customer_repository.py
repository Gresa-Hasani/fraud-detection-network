"""Customer node lookup, listing, and neighborhood queries."""

from __future__ import annotations

from typing import Any

from app.core.database import Neo4jConnection


class CustomerRepository:
    def __init__(self, connection: Neo4jConnection) -> None:
        self._db = connection

    def list_customers(
        self, fraud_status: str | None, country: str | None, limit: int, offset: int
    ) -> list[dict[str, Any]]:
        return self._db.run_query(
            """
            MATCH (c:Customer)
            WHERE ($fraud_status IS NULL OR c.fraud_status = $fraud_status)
              AND ($country IS NULL OR c.country = $country)
            RETURN c
            ORDER BY c.customer_id
            SKIP $offset
            LIMIT $limit
            """,
            {"fraud_status": fraud_status, "country": country, "limit": limit, "offset": offset},
        )

    def count_customers(self, fraud_status: str | None, country: str | None) -> int:
        result = self._db.run_query(
            """
            MATCH (c:Customer)
            WHERE ($fraud_status IS NULL OR c.fraud_status = $fraud_status)
              AND ($country IS NULL OR c.country = $country)
            RETURN count(c) AS n
            """,
            {"fraud_status": fraud_status, "country": country},
        )
        return result[0]["n"]

    def get_customer(self, customer_id: str) -> dict[str, Any] | None:
        result = self._db.run_query(
            "MATCH (c:Customer {customer_id: $customer_id}) RETURN c", {"customer_id": customer_id}
        )
        return result[0]["c"] if result else None

    def get_customer_devices(self, customer_id: str) -> list[dict[str, Any]]:
        return self._db.run_query(
            """
            MATCH (c:Customer {customer_id: $customer_id})-[r:USES_DEVICE]->(d:Device)
            RETURN d, r.first_seen AS first_seen, r.last_seen AS last_seen, r.usage_count AS usage_count
            ORDER BY usage_count DESC
            """,
            {"customer_id": customer_id},
        )
