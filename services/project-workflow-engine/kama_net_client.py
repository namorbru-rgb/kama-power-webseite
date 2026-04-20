"""Projekt- & Workflow-Engine — KAMA-net (Supabase) sync client."""
from __future__ import annotations

import structlog
import httpx

from config import settings

log = structlog.get_logger()

_HEADERS = {
    "apikey": settings.kama_net_api_key,
    "Authorization": f"Bearer {settings.kama_net_api_key}",
    "Content-Type": "application/json",
}


async def create_project(
    auftrag_kama_net_id: str,
    name: str,
    project_type: str,
    system_size: float | None,
) -> str | None:
    """
    Create a project record in KAMA-net (app_projects table via Supabase REST).
    Returns the new KAMA-net project ID, or None on failure.
    """
    if not settings.kama_net_api_key:
        log.warning("kama_net_api_key_not_set_skipping_project_create")
        return None

    payload = {
        "auftrag_id": auftrag_kama_net_id,
        "name": name,
        "project_type": project_type,
        "system_size_kwp": system_size,
        "status": "planning",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{settings.kama_net_url}/rest/v1/app_projects",
                headers={**_HEADERS, "Prefer": "return=representation"},
                json=payload,
            )
            resp.raise_for_status()
            rows = resp.json()
            if rows:
                kama_net_id = str(rows[0].get("id", ""))
                log.info("kama_net_project_created", kama_net_id=kama_net_id, name=name)
                return kama_net_id
    except Exception as exc:
        log.error("kama_net_project_create_failed", error=str(exc))

    return None


async def update_project_status(kama_net_project_id: str, status: str) -> None:
    """
    Sync current workflow status to fm_projektfortschritt in KAMA-net.
    status: 'planning' | 'in_progress' | 'completed' | 'on_hold'
    """
    if not settings.kama_net_api_key or not kama_net_project_id:
        return

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.patch(
                f"{settings.kama_net_url}/rest/v1/fm_projektfortschritt",
                headers=_HEADERS,
                params={"project_id": f"eq.{kama_net_project_id}"},
                json={"status": status, "updated_at": "now()"},
            )
            resp.raise_for_status()
            log.info(
                "kama_net_project_status_updated",
                kama_net_project_id=kama_net_project_id,
                status=status,
            )
    except Exception as exc:
        log.error(
            "kama_net_project_status_update_failed",
            kama_net_project_id=kama_net_project_id,
            error=str(exc),
        )
