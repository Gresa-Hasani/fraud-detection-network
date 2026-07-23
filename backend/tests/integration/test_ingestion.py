"""Integration tests for the CSV -> Neo4j ingestion pipeline.

Runs against a live Neo4j (skipped otherwise, see conftest.py) using the
small, committed `tests/fixtures/mini_dataset` fixture so it's fast and
doesn't depend on the large generated dataset being present.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from ingestion import loaders  # noqa: E402
from ingestion.validation import load_and_validate  # noqa: E402

from app.core.database import Neo4jConnection  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "mini_dataset"


def _import_fixture(connection: Neo4jConnection) -> loaders.ImportCounters:
    from import_dataset import NODE_FILES, RELATIONSHIP_FILES  # noqa: PLC0415

    total = loaders.ImportCounters()
    for filename, required, not_null, loader_fn in NODE_FILES + RELATIONSHIP_FILES:
        path = FIXTURE_DIR / filename
        if not path.exists():
            continue
        validated = load_and_validate(str(path), required, not_null)
        counters = loaders.ImportCounters()
        loader_fn(connection, validated.records, counters)
        total.nodes_created += counters.nodes_created
        total.relationships_created += counters.relationships_created
    return total


def _fixture_customer_ids() -> list[str]:
    customers_path = str(FIXTURE_DIR / "customers.csv")
    return [row["customer_id"] for row in load_and_validate(customers_path, ["customer_id"], ["customer_id"]).records]


@pytest.fixture(autouse=True)
def _clean_fixture_entities(neo4j_connection: Neo4jConnection):
    # Clean up before *and* after: another test module (test_fraud_detection_service.py) imports
    # this same fixture into a session-scoped fixture that only tears down at session end, so this
    # module can't assume it's the first thing to touch these customer ids.
    customer_ids = _fixture_customer_ids()

    def _remove() -> None:
        neo4j_connection.run_write_query(
            "MATCH (c:Customer) WHERE c.customer_id IN $ids DETACH DELETE c", {"ids": customer_ids}
        )

    _remove()
    yield
    _remove()


def test_ingestion_creates_nodes_and_relationships(neo4j_connection: Neo4jConnection) -> None:
    counters = _import_fixture(neo4j_connection)
    assert counters.nodes_created > 0
    assert counters.relationships_created > 0


def test_ingestion_is_idempotent(neo4j_connection: Neo4jConnection) -> None:
    _import_fixture(neo4j_connection)
    second_run = _import_fixture(neo4j_connection)
    assert second_run.nodes_created == 0
    assert second_run.relationships_created == 0


def test_constraints_reject_duplicate_customer_ids(neo4j_connection: Neo4jConnection) -> None:
    _import_fixture(neo4j_connection)
    some_customer_id = _fixture_customer_ids()[0]
    result = neo4j_connection.run_query(
        "MATCH (c:Customer {customer_id: $id}) RETURN count(c) AS n", {"id": some_customer_id}
    )
    assert result[0]["n"] == 1
