from __future__ import annotations

from pydantic import BaseModel


class TransactionOut(BaseModel):
    transaction_id: str
    amount: float
    currency: str
    timestamp: str
    transaction_type: str
    channel: str
    status: str
    country: str
    risk_score: int
    is_flagged: bool
