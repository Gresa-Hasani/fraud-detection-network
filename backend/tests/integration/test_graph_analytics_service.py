"""Integration tests for the Neo4j GDS pipeline. Requires the `graph-data-science` plugin
to be loaded (see docker-compose.yml) in addition to a live Neo4j instance.
"""

from __future__ import annotations

import pytest

from app.core.database import Neo4jConnection
from app.services.graph_analytics_service import GraphAnalyticsService


@pytest.fixture(scope="module")
def analytics_service(neo4j_connection: Neo4jConnection) -> GraphAnalyticsService:
    service = GraphAnalyticsService()
    yield service
    service.close()


@pytest.fixture(scope="module")
def analytics_summary(neo4j_connection: Neo4jConnection, analytics_service: GraphAnalyticsService) -> dict:
    accounts = neo4j_connection.run_query("MATCH (a:Account) RETURN count(a) AS n")[0]["n"]
    if accounts == 0:
        pytest.skip("No accounts loaded; run `make seed` first.")
    return analytics_service.run_all()


def test_projection_reports_nonzero_nodes_and_relationships(analytics_summary: dict) -> None:
    assert int(analytics_summary["nodes"]) > 0
    assert int(analytics_summary["relationships"]) > 0


def test_pagerank_writes_score_on_every_account(neo4j_connection: Neo4jConnection, analytics_summary: dict) -> None:
    result = neo4j_connection.run_query(
        "MATCH (a:Account) RETURN count(a) AS total, count(a.pagerank_score) AS scored"
    )[0]
    assert result["scored"] == result["total"]


def test_wcc_writes_a_component_id_on_every_account(neo4j_connection: Neo4jConnection, analytics_summary: dict) -> None:
    result = neo4j_connection.run_query(
        "MATCH (a:Account) RETURN count(a) AS total, count(a.wcc_component) AS labeled"
    )[0]
    assert result["labeled"] == result["total"]
    assert analytics_summary["wcc"]["component_count"] >= 1


def test_louvain_writes_a_community_id_consumable_by_fd010(
    neo4j_connection: Neo4jConnection, analytics_summary: dict
) -> None:
    result = neo4j_connection.run_query("MATCH (a:Account) RETURN count(a) AS total, count(a.community_id) AS labeled")[
        0
    ]
    assert result["labeled"] == result["total"]
    assert analytics_summary["louvain"]["community_count"] >= 1


def test_projection_is_dropped_after_run(neo4j_connection: Neo4jConnection, analytics_summary: dict) -> None:
    # run_all() always drops its projection in a finally block, regardless of which
    # algorithms ran -- a leaked in-memory graph would otherwise accumulate across runs.
    exists = neo4j_connection.run_query(
        "CALL gds.graph.exists('account-transaction-network') YIELD exists RETURN exists"
    )[0]["exists"]
    assert exists is False


def test_rerunning_projection_does_not_error(analytics_service: GraphAnalyticsService, analytics_summary: dict) -> None:
    # _project_account_network() drops any existing graph of the same name first, so this
    # must not raise "graph already exists".
    second_summary = analytics_service.run_all()
    assert int(second_summary["nodes"]) == int(analytics_summary["nodes"])
