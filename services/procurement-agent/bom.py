"""BOM Loader — fetches Bill of Materials from KAMA-net (Supabase).

Falls back to a default catalog when KAMA-net has no BOM configured for an order.
The default catalog maps system size (kWp) to standard component quantities.
"""
from __future__ import annotations

import httpx
import structlog

from config import settings
from models import BomItem

log = structlog.get_logger()


# ── Default BOM catalog ───────────────────────────────────────────────────────
# Standard quantities per kWp for a typical Swiss rooftop solar + BESS install.
# Override via KAMA-net app_bom for custom projects.

_MODULES_PER_KWP = 2.5          # ~400 Wp modules → 2.5 per kWp
_WR_PER_10KWP = 1.0             # one inverter per 10 kWp
_CABLE_METERS_PER_KWP = 8.0     # DC cabling estimate

DEFAULT_BOM_CATALOG = [
    {
        "article_id": "MOD-400W",
        "article_name": "Solarmodul 400 Wp",
        "qty_per_kwp": _MODULES_PER_KWP,
        "unit": "Stk",
        "supplier": "andercore",
    },
    {
        "article_id": "WR-10K",
        "article_name": "Wechselrichter 10 kW",
        "qty_per_kwp": _WR_PER_10KWP / 10,
        "unit": "Stk",
        "supplier": "solarmarkt",
    },
    {
        "article_id": "UK-ZIEGEL",
        "article_name": "UK Ziegel Montagesystem",
        "qty_per_kwp": _MODULES_PER_KWP,
        "unit": "Stk",
        "supplier": "tritec",
    },
    {
        "article_id": "CABLE-DC-6",
        "article_name": "DC-Kabel 6 mm²",
        "qty_per_kwp": _CABLE_METERS_PER_KWP,
        "unit": "m",
        "supplier": "solarmarkt",
    },
]


async def fetch_bom(auftrag_id: str, system_size_kwp: float | None = None) -> list[BomItem]:
    """Return BOM for a given order, falling back to default catalog."""
    items = await _fetch_from_kama_net(auftrag_id)
    if items:
        log.info("bom_loaded_from_kama_net", auftrag_id=auftrag_id, count=len(items))
        return items

    if system_size_kwp and system_size_kwp > 0:
        items = _default_bom(system_size_kwp)
        log.info(
            "bom_using_default_catalog",
            auftrag_id=auftrag_id,
            system_size_kwp=system_size_kwp,
            count=len(items),
        )
        return items

    log.warning("bom_empty", auftrag_id=auftrag_id)
    return []


async def _fetch_from_kama_net(auftrag_id: str) -> list[BomItem]:
    """Query Supabase REST API for app_bom entries belonging to this order."""
    if not settings.kama_net_api_key:
        return []

    url = f"{settings.kama_net_url}/rest/v1/app_bom"
    params = {"auftrag_id": f"eq.{auftrag_id}", "select": "article_id,article_name,qty_required,unit"}
    headers = {
        "apikey": settings.kama_net_api_key,
        "Authorization": f"Bearer {settings.kama_net_api_key}",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            rows = resp.json()
            return [BomItem(**r) for r in rows]
    except Exception as exc:
        log.warning("kama_net_bom_fetch_failed", auftrag_id=auftrag_id, error=str(exc))
        return []


def _default_bom(system_size_kwp: float) -> list[BomItem]:
    items: list[BomItem] = []
    for entry in DEFAULT_BOM_CATALOG:
        qty = round(entry["qty_per_kwp"] * system_size_kwp, 0)
        if qty < 1:
            qty = 1
        items.append(
            BomItem(
                article_id=entry["article_id"],
                article_name=entry["article_name"],
                qty_required=qty,
                unit=entry["unit"],
            )
        )
    return items
