"""Communication Agent — SOP creation and Supabase (KAMA-net) storage."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import httpx
import structlog

from config import settings
from models import CommSopRow

log = structlog.get_logger()


def build_sop_body(
    title: str,
    domain: str,
    trigger: str,
    steps: list[str],
    responsible: str,
    notes: str = "",
) -> str:
    """Render a standardised SOP markdown document."""
    step_lines = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(steps))
    notes_section = f"\n## Notizen\n{notes}" if notes else ""
    return (
        f"# SOP: {title}\n\n"
        f"**Domain:** {domain}  \n"
        f"**Verantwortlich:** {responsible}  \n"
        f"**Erstellt:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}  \n\n"
        f"## Auslöser\n{trigger}\n\n"
        f"## Schritte\n{step_lines}"
        f"{notes_section}\n"
    )


async def save_sop_to_kama_net(row: CommSopRow) -> str | None:
    """Upsert SOP to Supabase (kama_net_sop_table). Returns the Supabase record id or None."""
    if not settings.kama_net_api_key:
        log.warning("kama_net_api_key_not_set", sop_id=str(row.id))
        return None

    headers = {
        "apikey": settings.kama_net_api_key,
        "Authorization": f"Bearer {settings.kama_net_api_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    payload = {
        "id": str(row.id),
        "title": row.title,
        "domain": row.domain,
        "body": row.body,
        "version": row.version,
        "created_by": row.created_by,
    }

    url = f"{settings.kama_net_url}/rest/v1/{settings.kama_net_sop_table}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                headers=headers,
                json=payload,
                params={"on_conflict": "id"},
            )
        resp.raise_for_status()
        data = resp.json()
        kama_net_id = data[0]["id"] if data else str(row.id)
        log.info("sop_saved_to_kama_net", sop_id=str(row.id), kama_net_id=kama_net_id)
        return kama_net_id
    except Exception as exc:
        log.error("sop_kama_net_error", sop_id=str(row.id), error=str(exc))
        return None
