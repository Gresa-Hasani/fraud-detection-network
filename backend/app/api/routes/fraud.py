from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import Neo4jConnection, PaginationParams, get_connection, pagination_params
from app.core.exceptions import EntityNotFoundError, UnsupportedFraudRuleError
from app.core.fraud_rules_config import RULES
from app.repositories.fraud_repository import FraudRepository
from app.repositories.investigation_repository import InvestigationRepository
from app.schemas.common import PaginatedResponse
from app.services.fraud_detection_service import FraudDetectionService

router = APIRouter(prefix="/fraud", tags=["fraud"])

_RULE_RUNNERS = {
    "FD-001": "run_fd001_shared_device",
    "FD-002": "run_fd002_shared_ip",
    "FD-003": "run_fd003_circular_transfer",
    "FD-004": "run_fd004_rapid_pass_through",
    "FD-005": "run_fd005_fan_in",
    "FD-006": "run_fd006_fan_out",
    "FD-007": "run_fd007_structuring",
    "FD-008": "run_fd008_account_takeover",
    "FD-010": "run_fd010_suspicious_community",
}


def _investigations(connection: Neo4jConnection = Depends(get_connection)) -> InvestigationRepository:
    return InvestigationRepository(connection)


def _fraud_repo(connection: Neo4jConnection = Depends(get_connection)) -> FraudRepository:
    return FraudRepository(connection)


def _detection_service(connection: Neo4jConnection = Depends(get_connection)) -> FraudDetectionService:
    return FraudDetectionService(connection)


@router.post("/run-detection")
def run_detection(service: FraudDetectionService = Depends(_detection_service)) -> dict:
    return service.run_all()


@router.post("/run-rule/{rule_id}")
def run_rule(rule_id: str, service: FraudDetectionService = Depends(_detection_service)) -> dict:
    runner_name = _RULE_RUNNERS.get(rule_id)
    if runner_name is None:
        raise UnsupportedFraudRuleError(
            f"Unknown or unsupported fraud rule: {rule_id}", {"supported_rules": sorted(_RULE_RUNNERS)}
        )
    signals = getattr(service, runner_name)()
    created = service.persist_signals(signals)
    return {"rule_id": rule_id, "signals_found": len(signals), "alerts_created": created}


@router.get("/alerts")
def list_alerts(
    status: str | None = None,
    severity: str | None = None,
    pagination: PaginationParams = Depends(pagination_params),
    fraud_repo: FraudRepository = Depends(_fraud_repo),
) -> PaginatedResponse[dict]:
    rows = fraud_repo.list_alerts(status, severity, pagination.limit, pagination.offset)
    items = [{**row["alert"], "entity": row["entity"], "entity_labels": row["entity_labels"]} for row in rows]
    return PaginatedResponse(items=items, limit=pagination.limit, offset=pagination.offset, count=len(items))


@router.get("/alerts/{alert_id}")
def get_alert(alert_id: str, connection: Neo4jConnection = Depends(get_connection)) -> dict:
    rows = connection.run_query(
        "MATCH (alert:FraudAlert {alert_id: $alert_id}) "
        "OPTIONAL MATCH (alert)-[:ALERTS_ON]->(entity) "
        "RETURN alert, entity, labels(entity) AS entity_labels",
        {"alert_id": alert_id},
    )
    if not rows:
        raise EntityNotFoundError(f"Fraud alert {alert_id} was not found.")
    row = rows[0]
    return {**row["alert"], "entity": row["entity"], "entity_labels": row["entity_labels"]}


@router.get("/rules")
def list_rules() -> list[dict]:
    return [
        {"rule_id": r.rule_id, "name": r.name, "description": r.description, "weight": r.weight} for r in RULES.values()
    ]


@router.get("/statistics")
def get_statistics(connection: Neo4jConnection = Depends(get_connection)) -> dict:
    rows = connection.run_query(
        "MATCH (a:FraudAlert) RETURN a.rule_id AS rule_id, a.severity AS severity, count(a) AS n"
    )
    by_rule: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for row in rows:
        by_rule[row["rule_id"]] = by_rule.get(row["rule_id"], 0) + row["n"]
        by_severity[row["severity"]] = by_severity.get(row["severity"], 0) + row["n"]
    return {"total_alerts": sum(by_rule.values()), "by_rule": by_rule, "by_severity": by_severity}


@router.get("/communities")
def get_communities(
    min_size: int = Query(default=5, ge=2, le=1000),
    pagination: PaginationParams = Depends(pagination_params),
    investigations: InvestigationRepository = Depends(_investigations),
) -> list[dict]:
    return investigations.find_suspicious_communities(min_size=min_size, limit=pagination.limit)


@router.get("/shared-devices")
def get_shared_devices(
    minimum_customers: int = Query(default=5, ge=2, le=1000),
    investigations: InvestigationRepository = Depends(_investigations),
) -> list[dict]:
    return investigations.find_devices_shared_by_many_customers(minimum_customers)


@router.get("/shared-ips")
def get_shared_ips(
    minimum_customers: int = Query(default=5, ge=2, le=1000),
    investigations: InvestigationRepository = Depends(_investigations),
) -> list[dict]:
    return investigations.find_ips_shared_by_many_customers(minimum_customers)


@router.get("/circular-transfers")
def get_circular_transfers(investigations: InvestigationRepository = Depends(_investigations)) -> list[dict]:
    return investigations.find_circular_transfers()


@router.get("/rapid-movement")
def get_rapid_movement(investigations: InvestigationRepository = Depends(_investigations)) -> list[dict]:
    return investigations.find_rapid_pass_through_accounts()


@router.get("/structuring")
def get_structuring(investigations: InvestigationRepository = Depends(_investigations)) -> list[dict]:
    return investigations.find_structuring_transactions()
