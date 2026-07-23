from __future__ import annotations

from pydantic import BaseModel


class AccountOut(BaseModel):
    account_id: str
    account_number: str
    account_type: str
    currency: str
    balance: float
    status: str
    country: str
    risk_score: int
    risk_level: str


class AccountListItem(BaseModel):
    account_id: str
    account_type: str
    status: str
    risk_score: int
    risk_level: str
