"""Aggregation queries for the dashboard and analytics endpoints."""

from __future__ import annotations

from typing import Any

from app.core.database import Neo4jConnection


class AnalyticsService:
    def __init__(self, connection: Neo4jConnection) -> None:
        self._db = connection

    def dashboard_summary(self) -> dict[str, Any]:
        result = self._db.run_query(
            """
            CALL { MATCH (c:Customer) RETURN count(c) AS total_customers }
            CALL { MATCH (a:Account) RETURN count(a) AS total_accounts }
            CALL { MATCH (t:Transaction) RETURN count(t) AS total_transactions }
            CALL { MATCH (t:Transaction {is_flagged: true}) RETURN count(t) AS flagged_transactions }
            CALL { MATCH (a:FraudAlert {status: 'OPEN'}) RETURN count(a) AS open_alerts }
            CALL { MATCH (a:Account {risk_level: 'CRITICAL'}) RETURN count(a) AS critical_accounts }
            CALL { MATCH (a:Account) WHERE a.community_id IS NOT NULL
                   RETURN count(DISTINCT a.community_id) AS communities }
            CALL { MATCH (c:Customer {fraud_status: 'CONFIRMED_FRAUD'}) RETURN count(c) AS confirmed_fraud_customers }
            RETURN total_customers, total_accounts, total_transactions, flagged_transactions,
                   open_alerts, critical_accounts, communities, confirmed_fraud_customers
            """
        )
        return result[0] if result else {}

    def risk_distribution(self) -> list[dict[str, Any]]:
        return self._db.run_query(
            "MATCH (a:Account) RETURN a.risk_level AS risk_level, count(a) AS count ORDER BY count DESC"
        )

    def alerts_by_rule(self) -> list[dict[str, Any]]:
        return self._db.run_query(
            "MATCH (a:FraudAlert) RETURN a.rule_id AS rule_id, count(a) AS count ORDER BY count DESC"
        )

    def alerts_by_severity(self) -> list[dict[str, Any]]:
        return self._db.run_query(
            "MATCH (a:FraudAlert) RETURN a.severity AS severity, count(a) AS count ORDER BY count DESC"
        )

    def top_risky_accounts(self, limit: int) -> list[dict[str, Any]]:
        return self._db.run_query(
            """
            MATCH (a:Account)
            WHERE a.risk_score > 0
            RETURN a.account_id AS account_id, a.risk_score AS risk_score, a.risk_level AS risk_level
            ORDER BY a.risk_score DESC
            LIMIT $limit
            """,
            {"limit": limit},
        )

    def community_summary(self, limit: int) -> list[dict[str, Any]]:
        return self._db.run_query(
            """
            MATCH (a:Account)
            WHERE a.community_id IS NOT NULL
            WITH a.community_id AS community_id, collect(a) AS members
            RETURN community_id,
                   size(members) AS member_count,
                   size([m IN members WHERE m.risk_level IN ['HIGH', 'CRITICAL']]) AS high_risk_count,
                   round(reduce(s = 0.0, m IN members | s + coalesce(m.balance, 0.0)) * 100) / 100 AS total_balance
            ORDER BY member_count DESC
            LIMIT $limit
            """,
            {"limit": limit},
        )
