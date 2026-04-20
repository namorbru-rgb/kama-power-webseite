"""Montage Agent — material checklist from procurement_bom / KAMA-net."""
from __future__ import annotations

import asyncpg
import httpx
import structlog

from config import settings
from models import MaterialItem, MontagePositionRow
import uuid

log = structlog.get_logger()

# Minimum installation steps every project type requires regardless of BOM
_BASE_STEPS: dict[str, list[str]] = {
    "solar": [
        "Gerüst / Absturzsicherung aufbauen",
        "Dachanbindung / Unterkonstruktion montieren",
        "Solarmodule verlegen und befestigen",
        "DC-Verkabelung legen und beschriften",
        "Wechselrichter montieren und verdrahten",
        "AC-Anschluss Verteilung / Netzanmeldung",
        "Dachdeckerarbeiten / Dachdurchführungen abdichten",
        "Inbetriebnahme und Ertragsmessung",
    ],
    "bess": [
        "Stellplatz vorbereiten (Fundament, Belüftung)",
        "BESS-Rack einbringen und verankern",
        "DC-Busverdrahtung Batterie ↔ Wechselrichter",
        "Batteriemanagementsystem (BMS) konfigurieren",
        "AC-Anschluss und Schutzrelais",
        "Fernüberwachung (MQTT / KAMA-net) einrichten",
        "Inbetriebnahme und Kapazitätstest",
    ],
    "vzev": [
        "VZEV-Messkonzept prüfen",
        "Smart Meter / Zähler installieren",
        "Netzanmeldung DSO einreichen",
        "Abrechnungslogik in KAMA-net konfigurieren",
        "Teilnehmer informieren und onboarden",
    ],
    "combined": [
        "Gerüst / Absturzsicherung aufbauen",
        "Solarmodule montieren",
        "BESS-Rack einbringen",
        "DC-Verkabelung (PV + BESS)",
        "Wechselrichter installieren und parametrieren",
        "AC-Anschluss und Netzanmeldung",
        "VZEV-Messkonzept und Zähler",
        "Fernüberwachung einrichten",
        "Inbetriebnahme gesamt",
    ],
}


async def fetch_material_checklist(
    pool: asyncpg.Pool, auftrag_id: str
) -> list[MaterialItem]:
    """Load BOM items from procurement_bom (local DB mirror of KAMA-net)."""
    rows = await pool.fetch(
        """
        SELECT article_id, article_name, qty_required, unit
        FROM procurement_bom
        WHERE auftrag_id = $1
        ORDER BY article_name
        """,
        auftrag_id,
    )
    if rows:
        log.info("bom_loaded_from_db", auftrag_id=auftrag_id, items=len(rows))
        return [
            MaterialItem(
                article_id=r["article_id"],
                article_name=r["article_name"],
                qty_required=r["qty_required"],
                unit=r["unit"],
            )
            for r in rows
        ]

    # Fall back to KAMA-net REST if BOM not yet mirrored
    return await _fetch_from_kama_net(auftrag_id)


async def _fetch_from_kama_net(auftrag_id: str) -> list[MaterialItem]:
    if not settings.kama_net_api_key:
        log.warning("kama_net_api_key_missing", context="bom_fetch")
        return []

    url = (
        f"{settings.kama_net_url}/rest/v1/app_bom"
        f"?auftrag_id=eq.{auftrag_id}&select=article_id,article_name,qty_required,unit"
    )
    headers = {
        "apikey": settings.kama_net_api_key,
        "Authorization": f"Bearer {settings.kama_net_api_key}",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        log.warning("kama_net_bom_fetch_failed", error=str(exc))
        return []

    log.info("bom_loaded_from_kama_net", auftrag_id=auftrag_id, items=len(data))
    return [
        MaterialItem(
            article_id=d["article_id"],
            article_name=d["article_name"],
            qty_required=d["qty_required"],
            unit=d.get("unit", "Stk"),
        )
        for d in data
    ]


def build_positions(
    montage_id: uuid.UUID,
    project_type: str,
    materials: list[MaterialItem],
) -> list[MontagePositionRow]:
    """
    Combine standard installation steps + BOM items into position rows.
    Standard steps get sequence 1–N, material positions follow.
    """
    positions: list[MontagePositionRow] = []
    steps = _BASE_STEPS.get(project_type, _BASE_STEPS["solar"])

    for seq, step in enumerate(steps, start=1):
        positions.append(
            MontagePositionRow(
                montage_id=montage_id,
                description=step,
                sequence=seq,
            )
        )

    offset = len(steps) + 1
    for i, mat in enumerate(materials):
        positions.append(
            MontagePositionRow(
                montage_id=montage_id,
                article_id=mat.article_id,
                description=f"Material: {mat.article_name}",
                qty_required=mat.qty_required,
                unit=mat.unit,
                sequence=offset + i,
            )
        )

    return positions
