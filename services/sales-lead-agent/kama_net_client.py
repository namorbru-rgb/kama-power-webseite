"""KAMA-net / Supabase REST API client for the Sales & Lead Agent."""
from __future__ import annotations

import structlog
import httpx

from config import settings

log = structlog.get_logger()

_HEADERS = {
    "apikey": settings.kama_net_api_key,
    "Authorization": f"Bearer {settings.kama_net_api_key}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


async def sync_inquiry_status(
    kama_net_id: str,
    status: str,
    temperature: str | None = None,
) -> bool:
    """Update lead status (and optionally temperature) in KAMA-net app_inquiries."""
    if not settings.kama_net_api_key:
        log.warning("kama_net_not_configured", reason="no_api_key")
        return False

    url = f"{settings.kama_net_url}/rest/v1/{settings.kama_net_inquiries_table}"
    payload: dict = {"status": status}
    if temperature:
        payload["temperature"] = temperature

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.patch(
                url,
                headers={**_HEADERS, "Prefer": "return=minimal"},
                params={"id": f"eq.{kama_net_id}"},
                json=payload,
            )
            resp.raise_for_status()
            log.info(
                "kama_net_inquiry_updated",
                kama_net_id=kama_net_id,
                status=status,
                temperature=temperature,
            )
            return True
    except httpx.HTTPError as exc:
        log.error("kama_net_update_failed", kama_net_id=kama_net_id, error=str(exc))
        return False


async def create_order_in_kama_net(
    anfrage_kama_net_id: str,
    customer_name: str,
    project_type: str,
    system_size_kwp: float | None,
    contract_value_chf: float | None,
) -> str | None:
    """Create a new order record in KAMA-net app_orders.

    Returns the new order's kama_net_id on success, or None.
    """
    if not settings.kama_net_api_key:
        log.warning("kama_net_not_configured", reason="no_api_key")
        return None

    url = f"{settings.kama_net_url}/rest/v1/{settings.kama_net_orders_table}"
    payload = {
        "anfrage_id": anfrage_kama_net_id,
        "customer_name": customer_name,
        "project_type": project_type,
        "system_size_kwp": system_size_kwp,
        "contract_value_chf": contract_value_chf,
        "status": "new",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, headers=_HEADERS, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and data:
                new_id = str(data[0].get("id", ""))
                log.info("kama_net_order_created", auftrag_id=new_id, anfrage_id=anfrage_kama_net_id)
                return new_id
    except httpx.HTTPError as exc:
        log.error("kama_net_order_create_failed", anfrage_id=anfrage_kama_net_id, error=str(exc))

    return None


async def fetch_inquiry(kama_net_id: str) -> dict | None:
    """Fetch a single inquiry record from KAMA-net."""
    if not settings.kama_net_api_key:
        return None

    url = f"{settings.kama_net_url}/rest/v1/{settings.kama_net_inquiries_table}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                url,
                headers=_HEADERS,
                params={"id": f"eq.{kama_net_id}", "limit": "1"},
            )
            resp.raise_for_status()
            rows = resp.json()
            return rows[0] if rows else None
    except httpx.HTTPError as exc:
        log.error("kama_net_fetch_failed", kama_net_id=kama_net_id, error=str(exc))
        return None
