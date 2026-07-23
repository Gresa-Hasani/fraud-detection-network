"""Neo4j driver lifecycle management and a safe query-execution helper.

Route handlers and services never talk to the `neo4j` driver directly.
Everything goes through `Neo4jConnection`, which owns the driver, enforces
parameterized queries, and centralizes session handling so that connection
errors surface as typed exceptions instead of leaking driver internals.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from neo4j import Driver, GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable
from neo4j.time import Date, DateTime, Duration, Time

from app.core.config import Settings, get_settings
from app.core.exceptions import GraphQueryError, GraphUnavailableError

logger = logging.getLogger("app.database")


def _to_json_safe(value: Any) -> Any:
    """Recursively convert Neo4j temporal types to JSON-serializable strings.

    `Record.data()` flattens Node/Relationship values into plain dicts, but leaves any
    DateTime/Date/Time/Duration *property values* as `neo4j.time.*` objects, which FastAPI's
    JSON encoder doesn't know how to serialize -- every route that returns a node with a
    timestamp property would otherwise 500. Applied once here so no caller has to remember it.
    """
    if isinstance(value, DateTime | Date | Time):
        return value.isoformat()
    if isinstance(value, Duration):
        return str(value)
    if isinstance(value, dict):
        return {k: _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_json_safe(v) for v in value]
    return value


class Neo4jConnection:
    """Thin wrapper around the official Neo4j driver.

    Holds a single driver instance for the process lifetime (the driver
    already pools connections internally), and exposes a `run_query` helper
    that always uses parameters -- never string-built Cypher.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._driver: Driver | None = None

    def connect(self) -> None:
        if self._driver is not None:
            return
        self._driver = GraphDatabase.driver(
            self._settings.neo4j_uri,
            auth=(self._settings.neo4j_user, self._settings.neo4j_password),
        )
        logger.info("neo4j_driver_initialized uri=%s", self._settings.neo4j_uri)

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None
            logger.info("neo4j_driver_closed")

    def verify_connectivity(self) -> bool:
        if self._driver is None:
            self.connect()
        assert self._driver is not None
        try:
            self._driver.verify_connectivity()
            return True
        except ServiceUnavailable:
            return False

    def run_query(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
        database: str | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a parameterized Cypher query and return records as dicts.

        `query` must never be built via string concatenation/formatting with
        user input -- only `parameters` may carry variable data.
        """
        if self._driver is None:
            self.connect()
        assert self._driver is not None

        db_name = database or self._settings.neo4j_database
        try:
            with self._driver.session(database=db_name) as session:
                result = session.run(query, dict(parameters) if parameters else {})
                return [_to_json_safe(record.data()) for record in result]
        except ServiceUnavailable as exc:
            logger.error("neo4j_unavailable error=%s", exc)
            raise GraphUnavailableError("The graph database is currently unavailable.") from exc
        except Neo4jError as exc:
            logger.error("neo4j_query_failed code=%s message=%s", exc.code, exc.message)
            raise GraphQueryError(f"Graph query failed: {exc.code}") from exc

    def run_write_query(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
        database: str | None = None,
    ) -> dict[str, Any]:
        """Execute a write query inside an explicit transaction and return summary counters."""
        if self._driver is None:
            self.connect()
        assert self._driver is not None

        db_name = database or self._settings.neo4j_database

        def _work(tx: Any) -> dict[str, Any]:
            result = tx.run(query, parameters or {})
            records = [_to_json_safe(record.data()) for record in result]
            summary = result.consume()
            return {"records": records, "counters": summary.counters}

        try:
            with self._driver.session(database=db_name) as session:
                return session.execute_write(_work)
        except ServiceUnavailable as exc:
            raise GraphUnavailableError("The graph database is currently unavailable.") from exc
        except Neo4jError as exc:
            logger.error("neo4j_write_failed code=%s message=%s", exc.code, exc.message)
            raise GraphQueryError(f"Graph write failed: {exc.code}") from exc


_connection: Neo4jConnection | None = None


def get_connection() -> Neo4jConnection:
    """FastAPI dependency: returns the process-wide Neo4j connection."""
    global _connection
    if _connection is None:
        _connection = Neo4jConnection()
        _connection.connect()
    return _connection
