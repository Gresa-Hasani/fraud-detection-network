from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import Neo4jConnection, PaginationParams, get_connection, pagination_params
from app.core.exceptions import EntityNotFoundError
from app.schemas.common import PaginatedResponse
from app.services.customer_service import CustomerService

router = APIRouter(prefix="/customers", tags=["customers"])


def _service(connection: Neo4jConnection = Depends(get_connection)) -> CustomerService:
    return CustomerService(connection)


@router.get("")
def list_customers(
    fraud_status: str | None = None,
    country: str | None = None,
    pagination: PaginationParams = Depends(pagination_params),
    service: CustomerService = Depends(_service),
) -> PaginatedResponse[dict]:
    items, total = service.list_customers(fraud_status, country, pagination.limit, pagination.offset)
    return PaginatedResponse(items=items, limit=pagination.limit, offset=pagination.offset, count=total)


@router.get("/{customer_id}")
def get_customer(customer_id: str, service: CustomerService = Depends(_service)) -> dict:
    return service.get_customer(customer_id)


@router.get("/{customer_id}/accounts")
def get_customer_accounts(customer_id: str, service: CustomerService = Depends(_service)) -> list[dict]:
    return service.get_customer_accounts(customer_id)


@router.get("/{customer_id}/devices")
def get_customer_devices(customer_id: str, service: CustomerService = Depends(_service)) -> list[dict]:
    return service.get_customer_devices(customer_id)


@router.get("/{customer_id}/connections")
def get_customer_connections(customer_id: str, service: CustomerService = Depends(_service)) -> list[dict]:
    return service.get_customer_connections(customer_id)


@router.get("/{customer_id}/risk")
def get_customer_risk(customer_id: str, service: CustomerService = Depends(_service)) -> dict:
    customer = service.get_customer(customer_id, mask_pii=False)
    return {"customer_id": customer_id, "fraud_status": customer["fraud_status"]}


@router.get("/{customer_id}/fraud-path")
def get_customer_fraud_path(customer_id: str, service: CustomerService = Depends(_service)) -> dict:
    path = service.get_customer_fraud_path(customer_id)
    if path is None:
        raise EntityNotFoundError(f"No path to a confirmed fraud entity found for {customer_id}.")
    return path
