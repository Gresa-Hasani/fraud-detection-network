"""Shared response envelopes."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    limit: int
    offset: int
    count: int


class GraphNode(BaseModel):
    id: str
    label: str
    properties: dict[str, Any]


class GraphEdge(BaseModel):
    source: str
    target: str
    type: str
    properties: dict[str, Any] = {}


class InvestigationGraph(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
