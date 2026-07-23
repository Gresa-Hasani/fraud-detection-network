"""FraudCase CRUD and linking to alerts/customers/accounts/transactions.

FraudCase and FraudAlert are kept as separate node types: an alert is one rule's automated
finding, a case is an investigator's unit of work that can bundle multiple alerts (and the
customers/accounts/transactions they implicate) together with a status, priority, and
resolution. Collapsing them into one node would conflate "the system found something" with
"a human is working this," which need independent lifecycles.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.database import Neo4jConnection


class CaseRepository:
    def __init__(self, connection: Neo4jConnection) -> None:
        self._db = connection

    def create_case(
        self,
        title: str,
        description: str,
        case_type: str,
        priority: str,
        assigned_to: str,
        alert_ids: list[str],
        customer_ids: list[str],
        account_ids: list[str],
    ) -> dict[str, Any]:
        case_id = f"CASE-{uuid.uuid4().hex[:10].upper()}"
        now = datetime.now(UTC).isoformat()
        self._db.run_write_query(
            """
            CREATE (fc:FraudCase {
                case_id: $case_id, title: $title, description: $description, case_type: $case_type,
                status: 'OPEN', priority: $priority, created_at: datetime($now), updated_at: datetime($now),
                assigned_to: $assigned_to, resolution: ''
            })
            """,
            {
                "case_id": case_id,
                "title": title,
                "description": description,
                "case_type": case_type,
                "priority": priority,
                "assigned_to": assigned_to,
                "now": now,
            },
        )
        if alert_ids:
            self._db.run_write_query(
                """
                MATCH (fc:FraudCase {case_id: $case_id})
                UNWIND $alert_ids AS alert_id
                MATCH (a:FraudAlert {alert_id: alert_id})
                MERGE (fc)-[:CONTAINS_ALERT]->(a)
                """,
                {"case_id": case_id, "alert_ids": alert_ids},
            )
        for label, id_field, ids in (
            ("Customer", "customer_id", customer_ids),
            ("Account", "account_id", account_ids),
        ):
            if ids:
                self._db.run_write_query(
                    f"""
                    MATCH (fc:FraudCase {{case_id: $case_id}})
                    UNWIND $ids AS entity_id
                    MATCH (e:{label} {{{id_field}: entity_id}})
                    MERGE (fc)-[:INVESTIGATES]->(e)
                    """,
                    {"case_id": case_id, "ids": ids},
                )
        return self.get_case(case_id)  # type: ignore[return-value]

    def list_cases(self, status: str | None, limit: int, offset: int) -> list[dict[str, Any]]:
        return self._db.run_query(
            """
            MATCH (fc:FraudCase)
            WHERE $status IS NULL OR fc.status = $status
            RETURN fc
            ORDER BY fc.created_at DESC
            SKIP $offset
            LIMIT $limit
            """,
            {"status": status, "limit": limit, "offset": offset},
        )

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        result = self._db.run_query("MATCH (fc:FraudCase {case_id: $case_id}) RETURN fc", {"case_id": case_id})
        return result[0]["fc"] if result else None

    def update_case(self, case_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        if not fields:
            return self.get_case(case_id)
        set_clauses = ", ".join(f"fc.{key} = $params.{key}" for key in fields)
        self._db.run_write_query(
            f"""
            MATCH (fc:FraudCase {{case_id: $case_id}})
            SET {set_clauses}, fc.updated_at = datetime($now)
            """,
            {"case_id": case_id, "params": fields, "now": datetime.now(UTC).isoformat()},
        )
        return self.get_case(case_id)

    def link_alert(self, case_id: str, alert_id: str) -> bool:
        result = self._db.run_write_query(
            """
            MATCH (fc:FraudCase {case_id: $case_id})
            MATCH (a:FraudAlert {alert_id: $alert_id})
            MERGE (fc)-[:CONTAINS_ALERT]->(a)
            """,
            {"case_id": case_id, "alert_id": alert_id},
        )
        return bool(result["counters"].relationships_created > 0)

    def get_case_graph(self, case_id: str) -> dict[str, Any]:
        records = self._db.run_query(
            """
            MATCH (fc:FraudCase {case_id: $case_id})
            OPTIONAL MATCH (fc)-[:CONTAINS_ALERT]->(alert:FraudAlert)
            OPTIONAL MATCH (alert)-[:ALERTS_ON]->(alerted)
            OPTIONAL MATCH (fc)-[:INVESTIGATES]->(investigated)
            RETURN fc, collect(DISTINCT alert) AS alerts, collect(DISTINCT alerted) AS alerted_entities,
                   collect(DISTINCT investigated) AS investigated_entities
            """,
            {"case_id": case_id},
        )
        return records[0] if records else {}
