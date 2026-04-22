"""
Supabase REST client — read-only, anon key only.

Uses the PostgREST HTTP API exposed by Supabase.
All methods are async and use a shared httpx.AsyncClient per process.

Tables served (read-only):
  - app_fm_documents
  - app_projects
  - app_customers
  - app_solar_bss
"""
from typing import Any, Optional
import httpx
import structlog

from config import settings

log = structlog.get_logger()

# Module-level singleton; initialised lazily on first call.
_client: Optional[httpx.AsyncClient] = None

ALLOWED_TABLES = frozenset(
    {"app_fm_documents", "app_projects", "app_customers", "app_solar_bss"}
)


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=f"{settings.supabase_url}/rest/v1/",
            headers={
                "apikey": settings.supabase_anon_key,
                "Authorization": f"Bearer {settings.supabase_anon_key}",
                "Accept": "application/json",
            },
            timeout=httpx.Timeout(connect=5.0, read=settings.supabase_timeout_sec, write=5.0, pool=5.0),
        )
    return _client


async def close() -> None:
    """Close the shared client (call on app shutdown)."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None


async def _fetch(
    table: str,
    *,
    select: str = "*",
    filters: Optional[dict[str, str]] = None,
    limit: int = 100,
    offset: int = 0,
    order: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    Generic read helper for a single Supabase table.

    :param table:   Table name (must be in ALLOWED_TABLES).
    :param select:  PostgREST column selector, default "*".
    :param filters: Dict of PostgREST filter strings, e.g. {"status": "eq.active"}.
    :param limit:   Max rows to return (capped at 500).
    :param offset:  Row offset for pagination.
    :param order:   Sort expression, e.g. "created_at.desc".
    :raises ValueError: for unknown tables.
    :raises httpx.HTTPStatusError: for non-2xx responses.
    """
    if table not in ALLOWED_TABLES:
        raise ValueError(f"Table '{table}' is not in the allowed read list")

    limit = min(limit, 500)
    params: dict[str, str] = {"select": select, "limit": str(limit), "offset": str(offset)}
    if order:
        params["order"] = order
    if filters:
        params.update(filters)

    client = _get_client()
    log.debug("supabase_fetch", table=table, limit=limit, offset=offset)
    resp = await client.get(table, params=params)
    resp.raise_for_status()
    return resp.json()


# ── Public convenience functions ──────────────────────────────────────────────

async def list_customers(
    limit: int = 100,
    offset: int = 0,
    status: Optional[str] = None,
) -> list[dict[str, Any]]:
    filters: dict[str, str] = {}
    if status:
        filters["status"] = f"eq.{status}"
    return await _fetch("app_customers", filters=filters, limit=limit, offset=offset, order="created_at.desc")


async def list_projects(
    limit: int = 100,
    offset: int = 0,
    status: Optional[str] = None,
) -> list[dict[str, Any]]:
    filters: dict[str, str] = {}
    if status:
        filters["status"] = f"eq.{status}"
    return await _fetch("app_projects", filters=filters, limit=limit, offset=offset, order="created_at.desc")


async def list_fm_documents(
    limit: int = 100,
    offset: int = 0,
    project_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    filters: dict[str, str] = {}
    if project_id:
        filters["project_id"] = f"eq.{project_id}"
    return await _fetch("app_fm_documents", filters=filters, limit=limit, offset=offset, order="created_at.desc")


async def list_solar_bss(
    limit: int = 100,
    offset: int = 0,
    customer_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    filters: dict[str, str] = {}
    if customer_id:
        filters["customer_id"] = f"eq.{customer_id}"
    return await _fetch("app_solar_bss", filters=filters, limit=limit, offset=offset, order="created_at.desc")
