from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import Neo4jConnection, PaginationParams, get_connection, pagination_params
from app.schemas.common import PaginatedResponse
from app.services.transaction_service import TransactionService

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _service(connection: Neo4jConnection = Depends(get_connection)) -> TransactionService:
    return TransactionService(connection)


@router.get("")
def list_transactions(
    transaction_type: str | None = None,
    min_amount: float | None = None,
    start: str | None = None,
    end: str | None = None,
    pagination: PaginationParams = Depends(pagination_params),
    service: TransactionService = Depends(_service),
) -> PaginatedResponse[dict]:
    items = service.list_transactions(transaction_type, min_amount, start, end, pagination.limit, pagination.offset)
    return PaginatedResponse(items=items, limit=pagination.limit, offset=pagination.offset, count=len(items))


@router.get("/flagged")
def list_flagged_transactions(
    pagination: PaginationParams = Depends(pagination_params), service: TransactionService = Depends(_service)
) -> PaginatedResponse[dict]:
    items = service.list_flagged(pagination.limit, pagination.offset)
    return PaginatedResponse(items=items, limit=pagination.limit, offset=pagination.offset, count=len(items))


@router.get("/high-risk")
def list_high_risk_transactions(
    min_risk_score: int = Query(default=50, ge=0, le=100),
    pagination: PaginationParams = Depends(pagination_params),
    service: TransactionService = Depends(_service),
) -> PaginatedResponse[dict]:
    items = service.list_high_risk(min_risk_score, pagination.limit, pagination.offset)
    return PaginatedResponse(items=items, limit=pagination.limit, offset=pagination.offset, count=len(items))


@router.get("/{transaction_id}")
def get_transaction(transaction_id: str, service: TransactionService = Depends(_service)) -> dict:
    return service.get_transaction(transaction_id)
