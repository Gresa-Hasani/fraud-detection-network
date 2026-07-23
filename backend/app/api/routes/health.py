"""Health and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import Neo4jConnection, get_connection

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness check -- the API process is up."""
    return {"status": "ok"}


@router.get("/health/neo4j")
def health_neo4j(connection: Neo4jConnection = Depends(get_connection)) -> dict[str, str]:
    """Readiness check -- Neo4j is reachable."""
    is_up = connection.verify_connectivity()
    return {"status": "ok" if is_up else "unavailable", "neo4j": "connected" if is_up else "disconnected"}
