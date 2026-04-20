"""Inventory Checker — queries KAMA-net app_articles and computes purchase deltas."""
from __future__ import annotations

import httpx
import structlog

from config import settings
from models import ArticleStock, BomItem, DeltaItem

log = structlog.get_logger()

# Supplier catalog: maps article_id prefix/exact match → supplier name.
# Real mapping is loaded from KAMA-net; this is the static fallback.
_ARTICLE_SUPPLIER_MAP: dict[str, str] = {
    "MOD-400W": "andercore",
    "WR-10K": "solarmarkt",
    "UK-ZIEGEL": "tritec",
    "CABLE-DC-6": "solarmarkt",
}


async def fetch_stock(article_ids: list[str]) -> dict[str, ArticleStock]:
    """Return stock levels from KAMA-net app_articles keyed by article_id."""
    if not article_ids or not settings.kama_net_api_key:
        return {}

    url = f"{settings.kama_net_url}/rest/v1/app_articles"
    id_list = ",".join(f'"{a}"' for a in article_ids)
    params = {
        "article_id": f"in.({id_list})",
        "select": "article_id,article_name,stock_qty,unit,ek_price_chf",
    }
    headers = {
        "apikey": settings.kama_net_api_key,
        "Authorization": f"Bearer {settings.kama_net_api_key}",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            rows = resp.json()
            return {r["article_id"]: ArticleStock(**r) for r in rows}
    except Exception as exc:
        log.warning("kama_net_stock_fetch_failed", error=str(exc))
        return {}


def compute_deltas(bom: list[BomItem], stock: dict[str, ArticleStock]) -> list[DeltaItem]:
    """Compute what needs to be ordered: required - on_hand, grouped by supplier."""
    deltas: list[DeltaItem] = []
    for item in bom:
        on_hand = stock.get(item.article_id)
        current_stock = on_hand.stock_qty if on_hand else 0.0
        needed = item.qty_required - current_stock

        if needed <= 0:
            log.info(
                "article_in_stock",
                article_id=item.article_id,
                required=item.qty_required,
                on_hand=current_stock,
            )
            continue

        supplier = _resolve_supplier(item.article_id)
        deltas.append(
            DeltaItem(
                article_id=item.article_id,
                article_name=item.article_name,
                qty_to_order=needed,
                unit=item.unit,
                ek_price_chf=on_hand.ek_price_chf if on_hand else None,
                supplier=supplier,
            )
        )
        log.info(
            "article_delta",
            article_id=item.article_id,
            required=item.qty_required,
            on_hand=current_stock,
            to_order=needed,
            supplier=supplier,
        )

    return deltas


def _resolve_supplier(article_id: str) -> str:
    """Map article_id to canonical supplier name. Falls back to 'solarmarkt'."""
    if article_id in _ARTICLE_SUPPLIER_MAP:
        return _ARTICLE_SUPPLIER_MAP[article_id]
    # Prefix-based fallback
    for prefix, supplier in _ARTICLE_SUPPLIER_MAP.items():
        if article_id.startswith(prefix.split("-")[0]):
            return supplier
    return "solarmarkt"
