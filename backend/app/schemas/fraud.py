"""Pydantic models shared by the fraud detection service and (later) the API layer."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FraudSignal(BaseModel):
    """One rule's finding about one entity -- the atomic unit the risk scorer consumes."""

    rule_id: str
    rule_name: str
    entity_id: str
    entity_type: str
    score_contribution: int
    description: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    related_entity_ids: list[str] = Field(default_factory=list)
    detected_at: datetime


class RiskReason(BaseModel):
    rule_id: str
    rule_name: str
    score_contribution: int
    description: str


class RiskAssessment(BaseModel):
    """Explainable, reproducible risk score for one entity -- the shape the API returns."""

    entity_id: str
    entity_type: str
    risk_score: int
    risk_level: str
    reasons: list[RiskReason]
    related_entities: list[str]
    calculated_at: datetime
