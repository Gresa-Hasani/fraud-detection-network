"""Shared FastAPI dependencies (DB connection injection, pagination params)."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Query

from app.core.database import Neo4jConnection, get_connection

__all__ = ["Neo4jConnection", "get_connection", "PaginationParams", "pagination_params"]


@dataclass
class PaginationParams:
    limit: int
    offset: int


def pagination_params(
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaginationParams:
    return PaginationParams(limit=limit, offset=offset)
