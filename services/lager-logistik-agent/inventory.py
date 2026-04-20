"""Lager & Logistik Agent — KAMA-net inventory helpers."""
from __future__ import annotations

import structlog
import httpx

from config import settings
from models import ArticleStock, WarehouseEmployee

log = structlog.get_logger()


def _headers() -> dict[str, str]:
    return {
        "apikey": settings.kama_net_api_key,
        "Authorization": f"Bearer {settings.kama_net_api_key}",
        "Content-Type": "application/json",
    }


def parse_warehouse_contacts() -> list[WarehouseEmployee]:
    """Parse warehouse employee contacts from the config string.

    Format: "Name:telegram_id,Name2:telegram_id2"
    Falls back to empty list if not configured.
    """
    raw = settings.warehouse_employee_contacts.strip()
    if not raw:
        return []

    employees = []
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" in entry:
            name, tg_id = entry.split(":", 1)
            employees.append(
                WarehouseEmployee(name=name.strip(), telegram_chat_id=tg_id.strip())
            )
        else:
            employees.append(WarehouseEmployee(name=entry))
    return employees


async def fetch_warehouse_employees() -> list[WarehouseEmployee]:
    """Fetch warehouse employees from KAMA-net employee_profiles.

    Falls back to config-based contacts if API is not configured or fails.
    """
    if not settings.kama_net_api_key:
        return parse_warehouse_contacts()

    url = (
        f"{settings.kama_net_url}/rest/v1/{settings.kama_net_employees_table}"
        "?select=id,name,telegram_chat_id,phone,role"
        "&role=eq.lager"
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=_headers())
            if resp.status_code == 200:
                rows = resp.json()
                employees = [
                    WarehouseEmployee(
                        name=r.get("name", ""),
                        telegram_chat_id=r.get("telegram_chat_id"),
                        phone=r.get("phone"),
                    )
                    for r in rows
                ]
                if employees:
                    return employees
    except Exception as exc:
        log.warning("kama_net_employees_fetch_failed", error=str(exc))

    # Fall back to config-based contacts
    return parse_warehouse_contacts()


async def fetch_article_stock(article_ids: list[str]) -> list[ArticleStock]:
    """Fetch current stock levels from KAMA-net for a list of article IDs."""
    if not settings.kama_net_api_key or not article_ids:
        return []

    ids_filter = ",".join(f'"{aid}"' for aid in article_ids)
    url = (
        f"{settings.kama_net_url}/rest/v1/{settings.kama_net_articles_table}"
        f"?select=article_id,article_name,stock_qty,unit"
        f"&article_id=in.({ids_filter})"
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=_headers())
            if resp.status_code == 200:
                return [
                    ArticleStock(
                        article_id=r["article_id"],
                        article_name=r.get("article_name", ""),
                        stock_qty=float(r.get("stock_qty", 0)),
                        unit=r.get("unit", "Stk"),
                    )
                    for r in resp.json()
                ]
    except Exception as exc:
        log.warning("kama_net_stock_fetch_failed", error=str(exc))
    return []


async def update_kama_net_stock(
    article_id: str, qty_delta: float, unit: str
) -> bool:
    """Increment stock in KAMA-net app_articles using a RPC or upsert.

    Returns True on success.
    """
    if not settings.kama_net_api_key:
        return False

    url = f"{settings.kama_net_url}/rest/v1/rpc/increment_stock"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                headers=_headers(),
                json={"p_article_id": article_id, "p_qty": qty_delta},
            )
            if resp.status_code in (200, 204):
                return True
            log.warning(
                "kama_net_stock_update_failed",
                article_id=article_id,
                status=resp.status_code,
                body=resp.text[:200],
            )
    except Exception as exc:
        log.warning("kama_net_stock_update_error", article_id=article_id, error=str(exc))
    return False
