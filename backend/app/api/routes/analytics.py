from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import Neo4jConnection, get_connection
from app.repositories.investigation_repository import InvestigationRepository
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _service(connection: Neo4jConnection = Depends(get_connection)) -> AnalyticsService:
    return AnalyticsService(connection)


@router.get("/dashboard")
def get_dashboard(service: AnalyticsService = Depends(_service)) -> dict:
    return service.dashboard_summary()


@router.get("/risk-distribution")
def get_risk_distribution(service: AnalyticsService = Depends(_service)) -> list[dict]:
    return service.risk_distribution()


@router.get("/top-risky-accounts")
def get_top_risky_accounts(
    limit: int = Query(default=25, ge=1, le=200), service: AnalyticsService = Depends(_service)
) -> list[dict]:
    return service.top_risky_accounts(limit)


@router.get("/top-shared-devices")
def get_top_shared_devices(
    limit: int = Query(default=25, ge=1, le=200), connection: Neo4jConnection = Depends(get_connection)
) -> list[dict]:
    return InvestigationRepository(connection).find_top_shared_devices(limit)


@router.get("/top-shared-ips")
def get_top_shared_ips(
    limit: int = Query(default=25, ge=1, le=200), connection: Neo4jConnection = Depends(get_connection)
) -> list[dict]:
    return InvestigationRepository(connection).find_ips_shared_by_many_customers(minimum_customers=2)[:limit]


@router.get("/community-summary")
def get_community_summary(
    limit: int = Query(default=25, ge=1, le=200), service: AnalyticsService = Depends(_service)
) -> list[dict]:
    return service.community_summary(limit)


@router.get("/alerts-by-rule")
def get_alerts_by_rule(service: AnalyticsService = Depends(_service)) -> list[dict]:
    return service.alerts_by_rule()


@router.get("/alerts-by-severity")
def get_alerts_by_severity(service: AnalyticsService = Depends(_service)) -> list[dict]:
    return service.alerts_by_severity()
