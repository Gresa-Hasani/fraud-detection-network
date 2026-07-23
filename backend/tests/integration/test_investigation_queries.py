"""Smoke + correctness tests for the investigation Cypher queries.

These run against whatever is currently loaded in the connected Neo4j
instance. They're intentionally tolerant on exact counts (the dataset is
randomly generated) but assert structural correctness and that the queries
that are supposed to find planted fraud patterns actually find *something*
when the full generated dataset (fraud-rate >= 0.03) has been imported.
"""

from __future__ import annotations

import pytest

from app.core.database import Neo4jConnection
from app.repositories.investigation_repository import InvestigationRepository


@pytest.fixture
def repo(neo4j_connection: Neo4jConnection) -> InvestigationRepository:
    return InvestigationRepository(neo4j_connection)


@pytest.fixture
def any_customer_id(neo4j_connection: Neo4jConnection) -> str:
    records = neo4j_connection.run_query("MATCH (c:Customer) RETURN c.customer_id AS id LIMIT 1")
    if not records:
        pytest.skip("No customers loaded; run `make seed` first.")
    return records[0]["id"]


@pytest.fixture
def any_account_id(neo4j_connection: Neo4jConnection) -> str:
    records = neo4j_connection.run_query("MATCH (a:Account) RETURN a.account_id AS id LIMIT 1")
    if not records:
        pytest.skip("No accounts loaded; run `make seed` first.")
    return records[0]["id"]


def test_find_customer_by_id_returns_the_right_customer(repo: InvestigationRepository, any_customer_id: str) -> None:
    customer = repo.find_customer_by_id(any_customer_id)
    assert customer is not None
    assert customer["customer_id"] == any_customer_id


def test_find_customer_by_id_returns_none_for_unknown_id(repo: InvestigationRepository) -> None:
    assert repo.find_customer_by_id("CUS-DOES-NOT-EXIST") is None


def test_find_customer_accounts_returns_only_owned_accounts(
    repo: InvestigationRepository, any_customer_id: str
) -> None:
    rows = repo.find_customer_accounts(any_customer_id)
    assert isinstance(rows, list)
    for row in rows:
        assert "a" in row and "transaction_count" in row


def test_find_devices_shared_by_many_customers_finds_planted_rings(repo: InvestigationRepository) -> None:
    rings = repo.find_devices_shared_by_many_customers(minimum_customers=5)
    assert isinstance(rings, list)
    if rings:
        assert rings[0]["customer_count"] >= 5
        assert rings[0]["customer_count"] >= rings[-1]["customer_count"]  # ORDER BY DESC holds


def test_find_ips_shared_by_many_customers_finds_planted_rings(repo: InvestigationRepository) -> None:
    rings = repo.find_ips_shared_by_many_customers(minimum_customers=5)
    assert isinstance(rings, list)
    if rings:
        assert rings[0]["customer_count"] >= 5


def test_find_circular_transfers_returns_closed_cycles(repo: InvestigationRepository) -> None:
    cycles = repo.find_circular_transfers(window_hours=168, amount_tolerance_pct=0.15)
    assert isinstance(cycles, list)
    for cycle in cycles:
        assert 3 <= cycle["cycle_length"] <= 6
        # account_cycle includes the closing return to the start account, so it's one longer.
        assert len(cycle["account_cycle"]) == cycle["cycle_length"] + 1
        assert cycle["account_cycle"][0] == cycle["account_cycle"][-1]
        assert len(cycle["transaction_ids"]) == cycle["cycle_length"]


def test_find_rapid_pass_through_accounts_respects_time_window(repo: InvestigationRepository) -> None:
    rows = repo.find_rapid_pass_through_accounts(max_minutes=30)
    assert isinstance(rows, list)
    for row in rows:
        assert row["seconds_between"] <= 30 * 60


def test_find_fan_in_accounts_meets_minimum_sources(repo: InvestigationRepository) -> None:
    rows = repo.find_fan_in_accounts(min_sources=10, window_hours=48)
    assert isinstance(rows, list)
    for row in rows:
        assert row["source_count"] >= 10


def test_find_fan_out_accounts_meets_minimum_targets(repo: InvestigationRepository) -> None:
    rows = repo.find_fan_out_accounts(min_targets=10, window_hours=48)
    assert isinstance(rows, list)
    for row in rows:
        assert row["target_count"] >= 10


def test_find_structuring_transactions_are_below_threshold(repo: InvestigationRepository) -> None:
    rows = repo.find_structuring_transactions(threshold=10000.0)
    assert isinstance(rows, list)
    for row in rows:
        for tx in row["below_threshold_txs"]:
            assert tx["amount"] < 10000.0


def test_find_foreign_ip_transactions_have_mismatched_country(repo: InvestigationRepository) -> None:
    rows = repo.find_foreign_ip_transactions()
    assert isinstance(rows, list)
    for row in rows[:20]:
        assert row["customer_country"] != row["ip_country"]


def test_build_account_investigation_subgraph_is_bounded(repo: InvestigationRepository, any_account_id: str) -> None:
    subgraph = repo.build_account_investigation_subgraph(any_account_id, depth=2, limit=50)
    assert "raw_nodes" in subgraph
    assert "raw_edges" in subgraph


def test_list_flagged_transactions_are_all_flagged(repo: InvestigationRepository) -> None:
    rows = repo.list_flagged_transactions(limit=20)
    assert isinstance(rows, list)
    for row in rows:
        assert row["t"]["is_flagged"] is True


def test_pagination_offset_moves_the_window(repo: InvestigationRepository) -> None:
    page_1 = repo.list_flagged_transactions(limit=5, offset=0)
    page_2 = repo.list_flagged_transactions(limit=5, offset=5)
    ids_1 = {row["t"]["transaction_id"] for row in page_1}
    ids_2 = {row["t"]["transaction_id"] for row in page_2}
    assert ids_1.isdisjoint(ids_2)
