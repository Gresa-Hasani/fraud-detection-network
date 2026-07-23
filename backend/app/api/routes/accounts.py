from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import Neo4jConnection, PaginationParams, get_connection, pagination_params
from app.core.exceptions import EntityNotFoundError
from app.schemas.common import InvestigationGraph, PaginatedResponse
from app.services.account_service import AccountService
from app.services.fraud_detection_service import FraudDetectionService

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _service(connection: Neo4jConnection = Depends(get_connection)) -> AccountService:
    return AccountService(connection)


@router.get("")
def list_accounts(
    risk_level: str | None = None,
    status: str | None = None,
    pagination: PaginationParams = Depends(pagination_params),
    service: AccountService = Depends(_service),
) -> PaginatedResponse[dict]:
    items, total = service.list_accounts(risk_level, status, pagination.limit, pagination.offset)
    return PaginatedResponse(items=items, limit=pagination.limit, offset=pagination.offset, count=total)


@router.get("/{account_id}")
def get_account(account_id: str, service: AccountService = Depends(_service)) -> dict:
    return service.get_account(account_id)


@router.get("/{account_id}/transactions")
def get_account_transactions(
    account_id: str,
    pagination: PaginationParams = Depends(pagination_params),
    service: AccountService = Depends(_service),
) -> PaginatedResponse[dict]:
    items = service.get_account_transactions(account_id, pagination.limit, pagination.offset)
    return PaginatedResponse(items=items, limit=pagination.limit, offset=pagination.offset, count=len(items))


@router.get("/{account_id}/network")
def get_account_network(
    account_id: str,
    depth: int = Query(default=2, ge=1, le=3),
    limit: int = Query(default=100, ge=1, le=300),
    service: AccountService = Depends(_service),
) -> InvestigationGraph:
    return service.get_account_network(account_id, depth, limit)


@router.get("/{account_id}/risk")
def get_account_risk(
    account_id: str,
    account_service: AccountService = Depends(_service),
    connection: Neo4jConnection = Depends(get_connection),
) -> dict:
    account_service.get_account(account_id)
    detection_service = FraudDetectionService(connection)
    assessment = detection_service.assess_entity(account_id, "Account")
    if assessment is None:
        return {
            "account_id": account_id,
            "risk_score": 0,
            "risk_level": "LOW",
            "reasons": [],
            "related_entities": [],
        }
    body = assessment.model_dump()
    body["account_id"] = body.pop("entity_id")
    del body["entity_type"]
    return body


@router.get("/{account_id}/fraud-path")
def get_account_fraud_path(account_id: str, service: AccountService = Depends(_service)) -> dict:
    path = service.get_account_fraud_path(account_id)
    if path is None:
        raise EntityNotFoundError(f"No path to a confirmed fraud entity found for {account_id}.")
    return path


@router.get("/{account_id}/counterparties")
def get_account_counterparties(
    account_id: str,
    limit: int = Query(default=25, ge=1, le=200),
    service: AccountService = Depends(_service),
) -> list[dict]:
    return service.get_account_counterparties(account_id, limit)
