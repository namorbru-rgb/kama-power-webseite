"""
Supabase read-only views — FastAPI router
=========================================
Exposes KAMA-net Supabase data as read-only API endpoints.

Routes:
  GET /kama-net/customers               — list customers
  GET /kama-net/projects                — list projects
  GET /kama-net/projects/{project_id}/documents
                                        — documents for a project
  GET /kama-net/solar-bss               — solar BSS assets
  GET /kama-net/dashboard-summary       — aggregate summary for the dashboard

All routes are strictly read-only (GET).  No Supabase service-role key is ever
used here — only the anon key configured in settings.supabase_anon_key.
"""
from typing import Any, Optional

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

import supabase_client as sb

log = structlog.get_logger()
router = APIRouter(prefix="/kama-net", tags=["kama-net"])


# ── Response models ───────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    total_returned: int
    offset: int
    items: list[dict[str, Any]]


class DashboardSummary(BaseModel):
    customer_count: int
    project_count: int
    solar_bss_count: int
    document_count: int


# ── Helpers ───────────────────────────────────────────────────────────────────

def _not_configured() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail="Supabase integration not configured — set SUPABASE_ANON_KEY.",
    )


def _handle_supabase_error(exc: Exception) -> HTTPException:
    if isinstance(exc, httpx.HTTPStatusError):
        log.warning("supabase_http_error", status=exc.response.status_code, body=exc.response.text[:200])
        return HTTPException(status_code=502, detail=f"Upstream Supabase error: {exc.response.status_code}")
    log.error("supabase_error", error=str(exc))
    return HTTPException(status_code=502, detail="Supabase request failed")


def _check_configured() -> None:
    from config import settings
    if not settings.supabase_anon_key:
        raise _not_configured()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/customers", response_model=PaginatedResponse, summary="List KAMA-net customers (read-only)")
async def list_customers(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None, description="Filter by status, e.g. 'active'"),
) -> PaginatedResponse:
    _check_configured()
    try:
        items = await sb.list_customers(limit=limit, offset=offset, status=status)
    except Exception as exc:
        raise _handle_supabase_error(exc) from exc
    return PaginatedResponse(total_returned=len(items), offset=offset, items=items)


@router.get("/projects", response_model=PaginatedResponse, summary="List KAMA-net projects (read-only)")
async def list_projects(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None, description="Filter by status, e.g. 'active'"),
) -> PaginatedResponse:
    _check_configured()
    try:
        items = await sb.list_projects(limit=limit, offset=offset, status=status)
    except Exception as exc:
        raise _handle_supabase_error(exc) from exc
    return PaginatedResponse(total_returned=len(items), offset=offset, items=items)


@router.get(
    "/projects/{project_id}/documents",
    response_model=PaginatedResponse,
    summary="List FM documents for a project (read-only)",
)
async def list_project_documents(
    project_id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> PaginatedResponse:
    _check_configured()
    try:
        items = await sb.list_fm_documents(limit=limit, offset=offset, project_id=project_id)
    except Exception as exc:
        raise _handle_supabase_error(exc) from exc
    return PaginatedResponse(total_returned=len(items), offset=offset, items=items)


@router.get("/solar-bss", response_model=PaginatedResponse, summary="List solar BSS assets (read-only)")
async def list_solar_bss(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    customer_id: Optional[str] = Query(None, description="Filter by customer ID"),
) -> PaginatedResponse:
    _check_configured()
    try:
        items = await sb.list_solar_bss(limit=limit, offset=offset, customer_id=customer_id)
    except Exception as exc:
        raise _handle_supabase_error(exc) from exc
    return PaginatedResponse(total_returned=len(items), offset=offset, items=items)


@router.get(
    "/dashboard-summary",
    response_model=DashboardSummary,
    summary="Aggregate counts from all KAMA-net tables — for the energy dashboard",
)
async def dashboard_summary() -> DashboardSummary:
    """
    Returns row counts from all four KAMA-net tables in a single call.
    Used by the energy dashboard to display KAMA-net data availability.
    """
    _check_configured()
    try:
        customers, projects, documents, solar_bss = await _gather_counts()
    except Exception as exc:
        raise _handle_supabase_error(exc) from exc
    return DashboardSummary(
        customer_count=customers,
        project_count=projects,
        solar_bss_count=solar_bss,
        document_count=documents,
    )


async def _gather_counts() -> tuple[int, int, int, int]:
    import asyncio
    results = await asyncio.gather(
        sb.list_customers(limit=1),
        sb.list_projects(limit=1),
        sb.list_fm_documents(limit=1),
        sb.list_solar_bss(limit=1),
        return_exceptions=True,
    )
    counts: list[int] = []
    for r in results:
        if isinstance(r, Exception):
            log.warning("supabase_count_error", error=str(r))
            counts.append(-1)
        else:
            counts.append(len(r))
    return counts[0], counts[1], counts[2], counts[3]
