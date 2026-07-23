"""Customer-facing response schemas. PII fields are masked before leaving the service layer."""

from __future__ import annotations

from pydantic import BaseModel


class CustomerOut(BaseModel):
    customer_id: str
    full_name: str
    email: str
    phone: str
    country: str
    city: str
    kyc_status: str
    customer_status: str
    fraud_status: str
    registration_date: str


class CustomerListItem(BaseModel):
    customer_id: str
    full_name: str
    country: str
    fraud_status: str
    customer_status: str
