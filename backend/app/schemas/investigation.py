from __future__ import annotations

from pydantic import BaseModel, Field


class FraudCaseCreate(BaseModel):
    title: str
    description: str = ""
    case_type: str = "GENERAL"
    priority: str = "MEDIUM"
    assigned_to: str = "unassigned"
    alert_ids: list[str] = Field(default_factory=list)
    customer_ids: list[str] = Field(default_factory=list)
    account_ids: list[str] = Field(default_factory=list)


class FraudCaseUpdate(BaseModel):
    status: str | None = None
    priority: str | None = None
    assigned_to: str | None = None
    resolution: str | None = None


class FraudCaseOut(BaseModel):
    case_id: str
    title: str
    description: str
    case_type: str
    status: str
    priority: str
    created_at: str
    updated_at: str
    assigned_to: str
    resolution: str | None = None
