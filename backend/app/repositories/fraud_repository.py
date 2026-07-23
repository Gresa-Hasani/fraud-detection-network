"""Persists fraud signals as `FraudAlert` nodes and writes risk scores back onto entities.

Alert identity is deterministic (`ALERT-<rule_id>-<entity_type>-<entity_id>`), so re-running
detection MERGEs the same alert node instead of creating duplicates -- this is what makes
`fraud_detection_service.run_all()` safe to run repeatedly (e.g. on a schedule) without the
alert list growing unbounded.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.core.database import Neo4jConnection
from app.schemas.fraud import FraudSignal, RiskAssessment

# Node labels whose schema (per docs/graph-model.md) includes a `risk_score` property that
# detection should keep up to date. Customer only has `fraud_status`, not a numeric score.
_SCORABLE_LABELS = {"Account": "Account", "Device": "Device", "IPAddress": "IPAddress"}

_ENTITY_ID_FIELDS = {
    "Customer": "customer_id",
    "Account": "account_id",
    "Transaction": "transaction_id",
    "Device": "device_id",
    "IPAddress": "ip",
}

_ALERT_ANCHOR_MATCH = {
    "Customer": "MATCH (entity:Customer {customer_id: $entity_id})",
    "Account": "MATCH (entity:Account {account_id: $entity_id})",
    "Transaction": "MATCH (entity:Transaction {transaction_id: $entity_id})",
    "Device": "MATCH (entity:Device {device_id: $entity_id})",
    "IPAddress": "MATCH (entity:IPAddress {ip: $entity_id})",
}


def _severity_for_score(score: int) -> str:
    if score >= 75:
        return "CRITICAL"
    if score >= 50:
        return "HIGH"
    if score >= 25:
        return "MEDIUM"
    return "LOW"


class FraudRepository:
    def __init__(self, connection: Neo4jConnection) -> None:
        self._db = connection

    def upsert_alert(self, signal: FraudSignal) -> bool:
        """MERGE a FraudAlert for this (rule, entity) pair. Returns True if newly created."""
        anchor = _ALERT_ANCHOR_MATCH.get(signal.entity_type)
        if anchor is None:
            return False

        alert_id = f"ALERT-{signal.rule_id}-{signal.entity_type}-{signal.entity_id}"
        result = self._db.run_write_query(
            f"""
            {anchor}
            MERGE (alert:FraudAlert {{alert_id: $alert_id}})
            ON CREATE SET alert.created_at = datetime($detected_at), alert.status = 'OPEN'
            SET alert.alert_type = $rule_id,
                alert.severity = $severity,
                alert.description = $description,
                alert.score = $score,
                alert.rule_id = $rule_id,
                alert.evidence = $evidence_json
            MERGE (alert)-[:ALERTS_ON]->(entity)
            """,
            {
                "entity_id": signal.entity_id,
                "alert_id": alert_id,
                "detected_at": signal.detected_at.isoformat(),
                "rule_id": signal.rule_id,
                "severity": _severity_for_score(signal.score_contribution),
                "description": signal.description,
                "score": signal.score_contribution,
                "evidence_json": _to_json_safe(signal.evidence),
            },
        )
        return bool(result["counters"].nodes_created > 0)

    def upsert_alerts_batch(self, signals: list[FraudSignal], batch_size: int = 500) -> int:
        """Batched equivalent of `upsert_alert`, grouped by entity_type and UNWIND-MERGEd.

        A demo-scale run can produce thousands of signals (e.g. a widely-shared IP touches
        hundreds of accounts); persisting each with its own round trip is the dominant cost at
        that volume, so this is what `FraudDetectionService.run_all()` actually calls.
        """
        by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for signal in signals:
            id_field = _ENTITY_ID_FIELDS.get(signal.entity_type)
            if id_field is None:
                continue
            by_type[signal.entity_type].append(
                {
                    "entity_id": signal.entity_id,
                    "alert_id": f"ALERT-{signal.rule_id}-{signal.entity_type}-{signal.entity_id}",
                    "detected_at": signal.detected_at.isoformat(),
                    "rule_id": signal.rule_id,
                    "severity": _severity_for_score(signal.score_contribution),
                    "description": signal.description,
                    "score": signal.score_contribution,
                    "evidence_json": _to_json_safe(signal.evidence),
                }
            )

        created = 0
        for entity_type, rows in by_type.items():
            id_field = _ENTITY_ID_FIELDS[entity_type]
            for start in range(0, len(rows), batch_size):
                batch = rows[start : start + batch_size]
                result = self._db.run_write_query(
                    f"""
                    UNWIND $rows AS row
                    MATCH (entity:{entity_type} {{{id_field}: row.entity_id}})
                    MERGE (alert:FraudAlert {{alert_id: row.alert_id}})
                    ON CREATE SET alert.created_at = datetime(row.detected_at), alert.status = 'OPEN'
                    SET alert.alert_type = row.rule_id,
                        alert.severity = row.severity,
                        alert.description = row.description,
                        alert.score = row.score,
                        alert.rule_id = row.rule_id,
                        alert.evidence = row.evidence_json
                    MERGE (alert)-[:ALERTS_ON]->(entity)
                    """,
                    {"rows": batch},
                )
                created += result["counters"].nodes_created
        return created

    def apply_risk_assessment(self, assessment: RiskAssessment) -> None:
        """Write the normalized score/level back onto the entity, if its schema has a risk_score field."""
        label = _SCORABLE_LABELS.get(assessment.entity_type)
        if label is None:
            return
        id_field = _ENTITY_ID_FIELDS[label]
        self._db.run_write_query(
            f"""
            MATCH (entity:{label} {{{id_field}: $entity_id}})
            SET entity.risk_score = $risk_score,
                entity.risk_level = $risk_level,
                entity.last_risk_calculation = datetime($calculated_at)
            """,
            {
                "entity_id": assessment.entity_id,
                "risk_score": assessment.risk_score,
                "risk_level": assessment.risk_level,
                "calculated_at": assessment.calculated_at.isoformat(),
            },
        )

    def apply_risk_assessments_batch(self, assessments: list[RiskAssessment], batch_size: int = 500) -> None:
        """Batched equivalent of `apply_risk_assessment`, grouped by entity_type and UNWIND-SET."""
        by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for assessment in assessments:
            label = _SCORABLE_LABELS.get(assessment.entity_type)
            if label is None:
                continue
            by_type[label].append(
                {
                    "entity_id": assessment.entity_id,
                    "risk_score": assessment.risk_score,
                    "risk_level": assessment.risk_level,
                    "calculated_at": assessment.calculated_at.isoformat(),
                }
            )

        for label, rows in by_type.items():
            id_field = _ENTITY_ID_FIELDS[label]
            for start in range(0, len(rows), batch_size):
                batch = rows[start : start + batch_size]
                self._db.run_write_query(
                    f"""
                    UNWIND $rows AS row
                    MATCH (entity:{label} {{{id_field}: row.entity_id}})
                    SET entity.risk_score = row.risk_score,
                        entity.risk_level = row.risk_level,
                        entity.last_risk_calculation = datetime(row.calculated_at)
                    """,
                    {"rows": batch},
                )

    def list_alerts(
        self, status: str | None = None, severity: str | None = None, limit: int = 25, offset: int = 0
    ) -> list[dict[str, Any]]:
        return self._db.run_query(
            """
            MATCH (alert:FraudAlert)
            WHERE ($status IS NULL OR alert.status = $status)
              AND ($severity IS NULL OR alert.severity = $severity)
            OPTIONAL MATCH (alert)-[:ALERTS_ON]->(entity)
            RETURN alert, entity, labels(entity) AS entity_labels
            ORDER BY alert.created_at DESC
            SKIP $offset
            LIMIT $limit
            """,
            {"status": status, "severity": severity, "limit": max(1, min(limit, 200)), "offset": offset},
        )


def _to_json_safe(evidence: dict[str, Any]) -> str:
    import json

    return json.dumps(evidence, default=str)
