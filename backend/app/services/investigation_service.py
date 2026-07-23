from __future__ import annotations

from typing import Any

from app.core.database import Neo4jConnection
from app.core.exceptions import EntityNotFoundError, InvalidInputError
from app.repositories.case_repository import CaseRepository
from app.schemas.common import GraphEdge, GraphNode, InvestigationGraph
from app.schemas.investigation import FraudCaseCreate, FraudCaseUpdate

VALID_CASE_STATUSES = {"OPEN", "IN_REVIEW", "ESCALATED", "RESOLVED", "FALSE_POSITIVE"}


class InvestigationService:
    def __init__(self, connection: Neo4jConnection) -> None:
        self._repo = CaseRepository(connection)

    def create_case(self, payload: FraudCaseCreate) -> dict[str, Any]:
        return self._repo.create_case(
            title=payload.title,
            description=payload.description,
            case_type=payload.case_type,
            priority=payload.priority,
            assigned_to=payload.assigned_to,
            alert_ids=payload.alert_ids,
            customer_ids=payload.customer_ids,
            account_ids=payload.account_ids,
        )

    def list_cases(self, status: str | None, limit: int, offset: int) -> list[dict[str, Any]]:
        return [row["fc"] for row in self._repo.list_cases(status, limit, offset)]

    def get_case(self, case_id: str) -> dict[str, Any]:
        case = self._repo.get_case(case_id)
        if case is None:
            raise EntityNotFoundError(f"Investigation case {case_id} was not found.")
        return case

    def update_case(self, case_id: str, payload: FraudCaseUpdate) -> dict[str, Any]:
        self.get_case(case_id)
        fields = payload.model_dump(exclude_unset=True)
        if "status" in fields and fields["status"] not in VALID_CASE_STATUSES:
            raise InvalidInputError(
                f"Invalid case status: {fields['status']}", {"valid_statuses": sorted(VALID_CASE_STATUSES)}
            )
        updated = self._repo.update_case(case_id, fields)
        assert updated is not None
        return updated

    def link_alert(self, case_id: str, alert_id: str) -> bool:
        self.get_case(case_id)
        return self._repo.link_alert(case_id, alert_id)

    def get_case_graph(self, case_id: str) -> InvestigationGraph:
        record = self._repo.get_case_graph(case_id)
        if not record:
            raise EntityNotFoundError(f"Investigation case {case_id} was not found.")

        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        case = record["fc"]
        case_node_id = case["case_id"]
        nodes.append(GraphNode(id=case_node_id, label="FraudCase", properties=case))

        for alert in record.get("alerts") or []:
            if alert is None:
                continue
            nodes.append(GraphNode(id=alert["alert_id"], label="FraudAlert", properties=alert))
            edges.append(GraphEdge(source=case_node_id, target=alert["alert_id"], type="CONTAINS_ALERT"))

        for entity in (record.get("alerted_entities") or []) + (record.get("investigated_entities") or []):
            if entity is None:
                continue
            entity_id = _entity_business_id(entity)
            if entity_id and not any(n.id == entity_id for n in nodes):
                nodes.append(GraphNode(id=entity_id, label=_guess_label(entity), properties=entity))

        return InvestigationGraph(nodes=nodes, edges=edges)


def _entity_business_id(entity: dict[str, Any]) -> str | None:
    for field in ("customer_id", "account_id", "transaction_id", "device_id", "ip"):
        if field in entity:
            return str(entity[field])
    return None


def _guess_label(entity: dict[str, Any]) -> str:
    for field, label in (
        ("customer_id", "Customer"),
        ("account_id", "Account"),
        ("transaction_id", "Transaction"),
        ("device_id", "Device"),
        ("ip", "IPAddress"),
    ):
        if field in entity:
            return label
    return "Unknown"
