"""Account-facing business logic: not-found handling and risk explanation assembly."""

from __future__ import annotations

from typing import Any

from app.core.database import Neo4jConnection
from app.core.exceptions import EntityNotFoundError
from app.repositories.account_repository import AccountRepository
from app.repositories.investigation_repository import InvestigationRepository
from app.schemas.common import GraphEdge, GraphNode, InvestigationGraph


class AccountService:
    def __init__(self, connection: Neo4jConnection) -> None:
        self._repo = AccountRepository(connection)
        self._investigations = InvestigationRepository(connection)

    def list_accounts(
        self, risk_level: str | None, status: str | None, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._repo.list_accounts(risk_level, status, limit, offset)
        total = self._repo.count_accounts(risk_level, status)
        return [row["a"] for row in rows], total

    def get_account(self, account_id: str) -> dict[str, Any]:
        account = self._repo.get_account(account_id)
        if account is None:
            raise EntityNotFoundError(f"Account {account_id} was not found.")
        return account

    def get_account_transactions(self, account_id: str, limit: int, offset: int) -> list[dict[str, Any]]:
        self.get_account(account_id)
        return [row["t"] for row in self._repo.get_account_transactions(account_id, limit, offset)]

    def get_account_network(self, account_id: str, depth: int, limit: int) -> InvestigationGraph:
        self.get_account(account_id)
        raw = self._investigations.build_account_investigation_subgraph(account_id, depth, limit)

        nodes: list[GraphNode] = []
        business_id_by_element_id: dict[str, str] = {}
        for node in raw.get("raw_nodes", []):
            label = _primary_label(node["labels"])
            business_id = _node_business_id(label, node["properties"], node["element_id"])
            business_id_by_element_id[node["element_id"]] = business_id
            nodes.append(GraphNode(id=business_id, label=label, properties=node["properties"]))

        edges = [
            GraphEdge(
                source=business_id_by_element_id.get(rel["source_element_id"], rel["source_element_id"]),
                target=business_id_by_element_id.get(rel["target_element_id"], rel["target_element_id"]),
                type=rel["type"],
                properties=rel["properties"],
            )
            for rel in raw.get("raw_edges", [])
        ]
        return InvestigationGraph(nodes=nodes, edges=edges)

    def get_account_counterparties(self, account_id: str, limit: int) -> list[dict[str, Any]]:
        self.get_account(account_id)
        return self._investigations.get_account_counterparties(account_id, limit)

    def get_account_fraud_path(self, account_id: str) -> dict[str, Any] | None:
        owner = self._repo.get_account_owner(account_id)
        if owner is None:
            raise EntityNotFoundError(f"Account {account_id} was not found or has no owner.")
        return self._investigations.find_shortest_path_to_confirmed_fraud(owner["customer_id"])


_ID_FIELDS_BY_LABEL = {
    "Customer": "customer_id",
    "Account": "account_id",
    "Transaction": "transaction_id",
    "Device": "device_id",
    "IPAddress": "ip",
    "Merchant": "merchant_id",
    "PhoneNumber": "phone",
    "EmailAddress": "email",
    "Address": "address_id",
    "FraudAlert": "alert_id",
    "FraudCase": "case_id",
}


def _primary_label(labels: list[str]) -> str:
    for label in labels:
        if label in _ID_FIELDS_BY_LABEL:
            return label
    return labels[0] if labels else "Unknown"


def _node_business_id(label: str, properties: dict[str, Any], element_id: str) -> str:
    id_field = _ID_FIELDS_BY_LABEL.get(label)
    if id_field and id_field in properties:
        return str(properties[id_field])
    return element_id
