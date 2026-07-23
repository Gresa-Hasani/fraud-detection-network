"""End-to-end API tests: boot the real FastAPI app (TestClient) against the live Neo4j
connection used by every other integration test. Skipped automatically if the DB has no
data loaded (via the same fixture pattern used elsewhere) so a bare `pytest` run without
`make seed` doesn't fail these for the wrong reason.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.database import Neo4jConnection
from app.main import app


@pytest.fixture(scope="module")
def client(neo4j_connection: Neo4jConnection) -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def any_ids(neo4j_connection: Neo4jConnection) -> dict[str, str]:
    customer = neo4j_connection.run_query("MATCH (c:Customer) RETURN c.customer_id AS id LIMIT 1")
    account = neo4j_connection.run_query("MATCH (a:Account) RETURN a.account_id AS id LIMIT 1")
    transaction = neo4j_connection.run_query("MATCH (t:Transaction) RETURN t.transaction_id AS id LIMIT 1")
    if not (customer and account and transaction):
        pytest.skip("No data loaded; run `make seed` first.")
    return {
        "customer_id": customer[0]["id"],
        "account_id": account[0]["id"],
        "transaction_id": transaction[0]["id"],
    }


def test_health(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_schema_is_served(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "Neo4j Fraud Detection Network"


def test_list_customers_masks_pii(client: TestClient, any_ids: dict[str, str]) -> None:
    response = client.get("/api/v1/customers", params={"limit": 5})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] >= 1
    for item in body["items"]:
        assert "@" in item["email"]
        assert "*" in item["email"]


def test_get_customer_not_found_returns_typed_error(client: TestClient) -> None:
    response = client.get("/api/v1/customers/CUS-DOES-NOT-EXIST")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "ENTITY_NOT_FOUND"
    assert "request_id" in body["error"]


def test_get_customer_accounts(client: TestClient, any_ids: dict[str, str]) -> None:
    response = client.get(f"/api/v1/customers/{any_ids['customer_id']}/accounts")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_list_accounts_pagination(client: TestClient, any_ids: dict[str, str]) -> None:
    page_1 = client.get("/api/v1/accounts", params={"limit": 3, "offset": 0}).json()
    page_2 = client.get("/api/v1/accounts", params={"limit": 3, "offset": 3}).json()
    ids_1 = {item["account_id"] for item in page_1["items"]}
    ids_2 = {item["account_id"] for item in page_2["items"]}
    assert ids_1.isdisjoint(ids_2)


def test_get_account_not_found(client: TestClient) -> None:
    response = client.get("/api/v1/accounts/ACC-DOES-NOT-EXIST")
    assert response.status_code == 404


def test_get_account_risk_shape(client: TestClient, any_ids: dict[str, str]) -> None:
    response = client.get(f"/api/v1/accounts/{any_ids['account_id']}/risk")
    assert response.status_code == 200
    body = response.json()
    assert set(body) >= {"account_id", "risk_score", "risk_level", "reasons", "related_entities"}


def test_get_account_network_is_bounded(client: TestClient, any_ids: dict[str, str]) -> None:
    response = client.get(f"/api/v1/accounts/{any_ids['account_id']}/network", params={"depth": 1, "limit": 20})
    assert response.status_code == 200
    body = response.json()
    assert "nodes" in body and "edges" in body


def test_get_transaction(client: TestClient, any_ids: dict[str, str]) -> None:
    response = client.get(f"/api/v1/transactions/{any_ids['transaction_id']}")
    assert response.status_code == 200
    assert response.json()["transaction_id"] == any_ids["transaction_id"]


def test_list_flagged_transactions_are_all_flagged(client: TestClient) -> None:
    response = client.get("/api/v1/transactions/flagged", params={"limit": 10})
    assert response.status_code == 200
    for item in response.json()["items"]:
        assert item["is_flagged"] is True


def test_list_fraud_alerts_includes_entity_details(client: TestClient) -> None:
    """Regression test: a bare (unparameterized) `PaginatedResponse` return-type annotation
    silently strips dict keys pydantic doesn't recognize -- this caught `entity` being dropped
    from every alert in the list response even though the repository query fetched it."""
    response = client.get("/api/v1/fraud/alerts", params={"limit": 5})
    assert response.status_code == 200
    items = response.json()["items"]
    if not items:
        pytest.skip("No fraud alerts loaded; run `make detect-fraud` first.")
    for item in items:
        assert "entity" in item
        assert "entity_labels" in item
        if item["entity"] is not None:
            assert len(item["entity"]) > 0


def test_fraud_rules_catalog(client: TestClient) -> None:
    response = client.get("/api/v1/fraud/rules")
    assert response.status_code == 200
    rule_ids = {rule["rule_id"] for rule in response.json()}
    assert {"FD-001", "FD-003", "FD-008", "FD-010"} <= rule_ids


def test_run_unsupported_rule_returns_400(client: TestClient) -> None:
    response = client.post("/api/v1/fraud/run-rule/FD-999")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_FRAUD_RULE"


def test_analytics_dashboard_shape(client: TestClient) -> None:
    response = client.get("/api/v1/analytics/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert set(body) >= {"total_customers", "total_accounts", "total_transactions", "open_alerts"}


def test_investigation_lifecycle(client: TestClient) -> None:
    create = client.post("/api/v1/investigations", json={"title": "API test case", "description": "x"})
    assert create.status_code == 200
    case_id = create.json()["case_id"]

    get_resp = client.get(f"/api/v1/investigations/{case_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "OPEN"

    patch_resp = client.patch(f"/api/v1/investigations/{case_id}", json={"status": "IN_REVIEW"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "IN_REVIEW"

    invalid_patch = client.patch(f"/api/v1/investigations/{case_id}", json={"status": "NOT_A_STATUS"})
    assert invalid_patch.status_code == 422

    graph_resp = client.get(f"/api/v1/investigations/{case_id}/graph")
    assert graph_resp.status_code == 200
    assert any(n["id"] == case_id for n in graph_resp.json()["nodes"])
