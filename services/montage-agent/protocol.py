"""Montage Agent — Abnahmeprotokoll (acceptance protocol) generator."""
from __future__ import annotations

import asyncpg
import httpx
import structlog
from datetime import datetime, timezone

from config import settings
from models import MontageProtokollRow

log = structlog.get_logger()


def build_protokoll_body(
    auftrag_id: str,
    customer_name: str,
    technician_name: str | None,
    positions: list[asyncpg.Record],
    completed_at: datetime,
) -> str:
    """Render acceptance protocol as Markdown."""
    done_count = sum(1 for p in positions if p["status"] == "done")
    total_count = len(positions)
    date_str = completed_at.strftime("%d.%m.%Y")
    time_str = completed_at.strftime("%H:%M")

    lines = [
        "# Abnahmeprotokoll",
        "",
        f"**Auftrag:** {auftrag_id}  ",
        f"**Kunde:** {customer_name}  ",
        f"**Datum:** {date_str} {time_str} UTC  ",
        f"**Monteur:** {technician_name or 'n/a'}  ",
        f"**Abgeschlossen:** {done_count}/{total_count} Positionen",
        "",
        "---",
        "",
        "## Arbeitsschritte",
        "",
    ]

    for pos in positions:
        status_icon = "✅" if pos["status"] == "done" else "⬜"
        lines.append(
            f"{status_icon} **{pos['sequence']:02d}.** {pos['description']}"
        )
        if pos["notes"]:
            lines.append(f"   > {pos['notes']}")

    lines += [
        "",
        "---",
        "",
        "## Ergebnis",
        "",
        f"{'✅ Anlage vollständig in Betrieb genommen.' if done_count == total_count else '⚠️ Nicht alle Positionen abgeschlossen — bitte prüfen.'}",
        "",
        "_Dieses Protokoll wurde automatisch vom KAMA Montage-Agent erstellt._",
    ]

    return "\n".join(lines)


async def save_protokoll_to_kama_net(row: MontageProtokollRow) -> str | None:
    """Persist the protocol to KAMA-net sops table (reuse comm-agent pattern)."""
    if not settings.kama_net_api_key:
        log.warning("kama_net_api_key_missing", context="protokoll_save")
        return None

    url = f"{settings.kama_net_url}/rest/v1/sops"
    headers = {
        "apikey": settings.kama_net_api_key,
        "Authorization": f"Bearer {settings.kama_net_api_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    payload = {
        "title": f"Abnahmeprotokoll {row.auftrag_id}",
        "domain": "montage",
        "body": row.body_markdown,
        "source": "montage-agent",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            kama_net_id = data[0].get("id") if data else None
            log.info("protokoll_saved_to_kama_net", id=kama_net_id)
            return str(kama_net_id) if kama_net_id else None
    except Exception as exc:
        log.warning("protokoll_kama_net_save_failed", error=str(exc))
        return None


def build_meldewesen_trigger_payload(
    montage_id: str,
    auftrag_id: str,
    customer_name: str,
    technician_name: str | None,
    protokoll_id: str,
    completed_at: datetime,
) -> dict:
    """Build the comm.send_request payload to notify Meldewesen via internal channel."""
    return {
        "event": "comm.send_request",
        "channel": "internal",
        "recipient": "meldewesen-agent",
        "subject": f"Installationsanzeige bereit — Auftrag {auftrag_id}",
        "body": (
            f"Montage für Auftrag {auftrag_id} (Kunde: {customer_name}) "
            f"abgeschlossen am {completed_at.strftime('%d.%m.%Y')}. "
            f"Abnahmeprotokoll ID: {protokoll_id}. "
            f"Monteur: {technician_name or 'n/a'}. "
            "Bitte Installationsanzeige bei zuständigem Netzbetreiber einreichen."
        ),
        "context": {
            "trigger": "montage.completed",
            "montage_id": montage_id,
            "auftrag_id": auftrag_id,
            "protokoll_id": protokoll_id,
            "priority": "high",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
