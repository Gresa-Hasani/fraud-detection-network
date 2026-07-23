"""Fraud-scenario tests: run the full detection engine against the committed mini fixture
and confirm each planted pattern (see tests/fixtures/mini_dataset/fraud_ground_truth.csv) is
actually detected, that a clean unrelated account is *not* flagged, and that a second run
does not create duplicate alerts.

The fixture is imported once per test session (session-scoped fixture) since it's the
`FraudDetectionService.run_all()` call -- which reads the whole graph -- that's expensive,
not the individual assertions.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

from app.core.database import Neo4jConnection
from app.services.fraud_detection_service import FraudDetectionService

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from ingestion import loaders  # noqa: E402
from ingestion.validation import load_and_validate  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "mini_dataset"


def _ground_truth() -> list[dict[str, str]]:
    with open(FIXTURE_DIR / "fraud_ground_truth.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _accounts_for_scenario(scenario: str) -> set[str]:
    return {
        row["entity_id"]
        for row in _ground_truth()
        if row["fraud_scenario"] == scenario and row["entity_type"] == "Account"
    }


def _import_fixture(connection: Neo4jConnection) -> None:
    from import_dataset import NODE_FILES, RELATIONSHIP_FILES  # noqa: PLC0415

    for filename, required, not_null, loader_fn in NODE_FILES + RELATIONSHIP_FILES:
        path = FIXTURE_DIR / filename
        if not path.exists():
            continue
        validated = load_and_validate(str(path), required, not_null)
        loader_fn(connection, validated.records, loaders.ImportCounters())


@pytest.fixture(scope="session")
def detection_summary(neo4j_connection: Neo4jConnection) -> dict:
    _import_fixture(neo4j_connection)
    service = FraudDetectionService(neo4j_connection)
    summary = service.run_all()
    yield summary
    customer_ids = [
        row["customer_id"]
        for row in load_and_validate(str(FIXTURE_DIR / "customers.csv"), ["customer_id"], ["customer_id"]).records
    ]
    neo4j_connection.run_write_query(
        "MATCH (c:Customer) WHERE c.customer_id IN $ids "
        "OPTIONAL MATCH (c)-[:OWNS]->(a:Account) "
        "OPTIONAL MATCH (alert:FraudAlert)-[:ALERTS_ON]->(a) "
        "DETACH DELETE c, a, alert",
        {"ids": customer_ids},
    )


@pytest.fixture(scope="session")
def flagged_account_ids(neo4j_connection: Neo4jConnection, detection_summary: dict) -> dict[str, set[str]]:
    """rule_id -> set of account_ids that have an OPEN FraudAlert for that rule."""
    rows = neo4j_connection.run_query(
        "MATCH (alert:FraudAlert)-[:ALERTS_ON]->(a:Account) RETURN alert.rule_id AS rule_id, a.account_id AS account_id"
    )
    grouped: dict[str, set[str]] = {}
    for row in rows:
        grouped.setdefault(row["rule_id"], set()).add(row["account_id"])
    return grouped


def test_shared_device_detection(flagged_account_ids: dict[str, set[str]]) -> None:
    expected = _accounts_for_scenario("SHARED_DEVICE_RING")
    assert expected & flagged_account_ids.get("FD-001", set())


def test_shared_ip_detection(flagged_account_ids: dict[str, set[str]]) -> None:
    expected = _accounts_for_scenario("SHARED_IP")
    assert expected & flagged_account_ids.get("FD-002", set())


def test_circular_transfer_detection(flagged_account_ids: dict[str, set[str]]) -> None:
    expected = _accounts_for_scenario("CIRCULAR_TRANSFER")
    assert expected & flagged_account_ids.get("FD-003", set())


def test_rapid_pass_through_detection(flagged_account_ids: dict[str, set[str]]) -> None:
    expected = _accounts_for_scenario("RAPID_PASS_THROUGH")
    assert expected & flagged_account_ids.get("FD-004", set())


def test_fan_in_detection(flagged_account_ids: dict[str, set[str]]) -> None:
    expected = _accounts_for_scenario("FAN_IN")
    assert expected & flagged_account_ids.get("FD-005", set())


def test_fan_out_detection(flagged_account_ids: dict[str, set[str]]) -> None:
    expected = _accounts_for_scenario("FAN_OUT")
    assert expected & flagged_account_ids.get("FD-006", set())


def test_structuring_detection(flagged_account_ids: dict[str, set[str]]) -> None:
    expected = _accounts_for_scenario("STRUCTURING")
    assert expected & flagged_account_ids.get("FD-007", set())


def test_account_takeover_detection(flagged_account_ids: dict[str, set[str]]) -> None:
    expected = _accounts_for_scenario("ACCOUNT_TAKEOVER")
    assert expected & flagged_account_ids.get("FD-008", set())


def test_shortest_path_to_fraud_detection(flagged_account_ids: dict[str, set[str]]) -> None:
    # Ground truth records the proximity scenario against the Customer, not an Account directly.
    proximity_customer_ids = {row["entity_id"] for row in _ground_truth() if row["fraud_scenario"] == "FRAUD_PROXIMITY"}
    assert proximity_customer_ids, "fixture should contain at least one FRAUD_PROXIMITY entity"

    with open(FIXTURE_DIR / "customer_accounts.csv", newline="", encoding="utf-8") as f:
        proximity_account_ids = {
            row["account_id"] for row in csv.DictReader(f) if row["customer_id"] in proximity_customer_ids
        }
    assert proximity_account_ids & flagged_account_ids.get("FD-009", set())


def test_clean_customer_is_not_flagged_by_shared_device_rule(flagged_account_ids: dict[str, set[str]]) -> None:
    fraud_customer_ids = {row["entity_id"] for row in _ground_truth() if row["entity_type"] == "Customer"}
    with open(FIXTURE_DIR / "customers.csv", newline="", encoding="utf-8") as f:
        all_customer_ids = {row["customer_id"] for row in csv.DictReader(f)}
    clean_customer_id = next(iter(all_customer_ids - fraud_customer_ids))

    with open(FIXTURE_DIR / "customer_accounts.csv", newline="", encoding="utf-8") as f:
        clean_account_ids = {row["account_id"] for row in csv.DictReader(f) if row["customer_id"] == clean_customer_id}

    # A customer never involved in any planted scenario should never pick up a shared-device
    # alert -- their account isn't in the fixture's device-ring evidence at all.
    assert clean_account_ids.isdisjoint(flagged_account_ids.get("FD-001", set()))


def test_rerun_does_not_duplicate_alerts(neo4j_connection: Neo4jConnection, detection_summary: dict) -> None:
    before = neo4j_connection.run_query("MATCH (a:FraudAlert) RETURN count(a) AS n")[0]["n"]
    service = FraudDetectionService(neo4j_connection)
    service.run_all()
    after = neo4j_connection.run_query("MATCH (a:FraudAlert) RETURN count(a) AS n")[0]["n"]
    assert after == before
