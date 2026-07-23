"""Shared fixtures for integration tests that need a live Neo4j instance.

These tests are skipped automatically if Neo4j is unreachable (e.g. in an
environment where `docker compose up neo4j` hasn't been run), so `pytest`
still succeeds without a database for quick unit-test-only runs.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.core.database import Neo4jConnection


@pytest.fixture(scope="session")
def neo4j_connection() -> Iterator[Neo4jConnection]:
    connection = Neo4jConnection()
    connection.connect()
    if not connection.verify_connectivity():
        connection.close()
        pytest.skip("Neo4j is not reachable; start it with `docker compose up -d neo4j`.")
    yield connection
    connection.close()
