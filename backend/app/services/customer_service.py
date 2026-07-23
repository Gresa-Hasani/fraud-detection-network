"""Customer-facing business logic: not-found handling, PII masking, and evidence assembly."""

from __future__ import annotations

from typing import Any

from app.core.database import Neo4jConnection
from app.core.exceptions import EntityNotFoundError
from app.repositories.customer_repository import CustomerRepository
from app.repositories.investigation_repository import InvestigationRepository


def mask_email(email: str) -> str:
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    return f"{local[:1]}***@{domain}"


def mask_phone(phone: str) -> str:
    if len(phone) <= 4:
        return "*" * len(phone)
    return phone[:4] + "*" * (len(phone) - 6) + phone[-2:]


class CustomerService:
    def __init__(self, connection: Neo4jConnection) -> None:
        self._repo = CustomerRepository(connection)
        self._investigations = InvestigationRepository(connection)

    def list_customers(
        self, fraud_status: str | None, country: str | None, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._repo.list_customers(fraud_status, country, limit, offset)
        total = self._repo.count_customers(fraud_status, country)
        customers = []
        for row in rows:
            customer = dict(row["c"])
            customer["email"] = mask_email(customer.get("email", ""))
            customer["phone"] = mask_phone(customer.get("phone", ""))
            customers.append(customer)
        return customers, total

    def get_customer(self, customer_id: str, mask_pii: bool = True) -> dict[str, Any]:
        customer = self._repo.get_customer(customer_id)
        if customer is None:
            raise EntityNotFoundError(f"Customer {customer_id} was not found.")
        if mask_pii:
            customer = dict(customer)
            customer["email"] = mask_email(customer.get("email", ""))
            customer["phone"] = mask_phone(customer.get("phone", ""))
        return customer

    def get_customer_accounts(self, customer_id: str) -> list[dict[str, Any]]:
        self.get_customer(customer_id)
        return [row["a"] for row in self._investigations.find_customer_accounts(customer_id)]

    def get_customer_devices(self, customer_id: str) -> list[dict[str, Any]]:
        self.get_customer(customer_id)
        return self._repo.get_customer_devices(customer_id)

    def get_customer_connections(self, customer_id: str) -> list[dict[str, Any]]:
        self.get_customer(customer_id)
        return self._investigations.find_customers_sharing_address_or_phone(customer_id)

    def get_customer_fraud_path(self, customer_id: str) -> dict[str, Any] | None:
        self.get_customer(customer_id)
        return self._investigations.find_shortest_path_to_confirmed_fraud(customer_id)
