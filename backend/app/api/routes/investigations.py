from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import Neo4jConnection, PaginationParams, get_connection, pagination_params
from app.core.exceptions import EntityNotFoundError
from app.schemas.common import InvestigationGraph, PaginatedResponse
from app.schemas.investigation import FraudCaseCreate, FraudCaseUpdate
from app.services.investigation_service import InvestigationService

router = APIRouter(prefix="/investigations", tags=["investigations"])


def _service(connection: Neo4jConnection = Depends(get_connection)) -> InvestigationService:
    return InvestigationService(connection)


@router.post("")
def create_investigation(payload: FraudCaseCreate, service: InvestigationService = Depends(_service)) -> dict:
    return service.create_case(payload)


@router.get("")
def list_investigations(
    status: str | None = None,
    pagination: PaginationParams = Depends(pagination_params),
    service: InvestigationService = Depends(_service),
) -> PaginatedResponse[dict]:
    items = service.list_cases(status, pagination.limit, pagination.offset)
    return PaginatedResponse(items=items, limit=pagination.limit, offset=pagination.offset, count=len(items))


@router.get("/{case_id}")
def get_investigation(case_id: str, service: InvestigationService = Depends(_service)) -> dict:
    return service.get_case(case_id)


@router.patch("/{case_id}")
def update_investigation(
    case_id: str, payload: FraudCaseUpdate, service: InvestigationService = Depends(_service)
) -> dict:
    return service.update_case(case_id, payload)


@router.post("/{case_id}/alerts/{alert_id}")
def link_alert_to_investigation(case_id: str, alert_id: str, service: InvestigationService = Depends(_service)) -> dict:
    linked = service.link_alert(case_id, alert_id)
    if not linked:
        raise EntityNotFoundError(f"Alert {alert_id} was not found (or already linked to case {case_id}).")
    return {"case_id": case_id, "alert_id": alert_id, "linked": True}


@router.get("/{case_id}/graph")
def get_investigation_graph(case_id: str, service: InvestigationService = Depends(_service)) -> InvestigationGraph:
    return service.get_case_graph(case_id)
