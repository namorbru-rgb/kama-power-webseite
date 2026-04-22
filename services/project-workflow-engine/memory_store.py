"""Agent Memory Store — async read/write via Supabase REST API (Service Role Key).

Usage pattern (heartbeat / long-running service):
    On start  — call read_memory()  to load context from prior runs.
    On stop   — call write_memory_item() + optional write_snapshot() to persist.
    On events — call append_memory_event() for decisions / blockers / status changes.

ENV vars required (set via .env or container env):
    SUPABASE_URL               — Supabase project URL (e.g. https://xxx.supabase.co)
    SUPABASE_SERVICE_ROLE_KEY  — Service Role secret (never expose to frontend)
    AGENT_MEMORY_ENABLED       — "true" to activate (default: off for safety)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

log = structlog.get_logger()


def _headers(service_role_key: str) -> dict[str, str]:
    return {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json",
    }


async def read_memory(
    supabase_url: str,
    service_role_key: str,
    agent_id: str,
    scope: str = "global",
    limit: int = 20,
    source_issue_id: str | None = None,
) -> list[dict[str, Any]]:
    """Load top-N most relevant memory items for this agent at run start.

    Returns an empty list if Supabase is unreachable or credentials are missing
    so the caller can continue without crashing.
    """
    if not supabase_url or not service_role_key:
        log.debug("agent_memory_read_skipped", reason="not_configured")
        return []

    params: dict[str, str] = {
        "agent_id": f"eq.{agent_id}",
        "scope": f"eq.{scope}",
        "order": "last_used_at.desc",
        "limit": str(limit),
        "select": "id,kind,summary,details_json,importance,source_issue_id,last_used_at",
    }
    if source_issue_id:
        params["source_issue_id"] = f"eq.{source_issue_id}"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{supabase_url}/rest/v1/agent_memory_items",
                headers=_headers(service_role_key),
                params=params,
            )
        if resp.status_code == 200:
            items = resp.json()
            log.info("agent_memory_loaded", agent_id=agent_id, scope=scope, count=len(items))
            return items
        log.warning(
            "agent_memory_read_failed",
            status=resp.status_code,
            body=resp.text[:200],
        )
    except Exception as exc:
        log.warning("agent_memory_read_error", error=str(exc))
    return []


async def write_memory_item(
    supabase_url: str,
    service_role_key: str,
    agent_id: str,
    kind: str,
    summary: str,
    scope: str = "global",
    details_json: dict[str, Any] | None = None,
    importance: int = 5,
    source_issue_id: str | None = None,
    source_run_id: str | None = None,
) -> None:
    """Upsert a memory item (call at run end or after key decisions)."""
    if not supabase_url or not service_role_key:
        return

    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "agent_id": agent_id,
        "scope": scope,
        "kind": kind,
        "summary": summary,
        "details_json": details_json,
        "importance": max(1, min(10, importance)),
        "source_issue_id": source_issue_id,
        "source_run_id": source_run_id,
        "last_used_at": now,
        "updated_at": now,
    }
    headers = {
        **_headers(service_role_key),
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{supabase_url}/rest/v1/agent_memory_items",
                headers=headers,
                json=payload,
            )
        if resp.status_code in (200, 201):
            log.debug("agent_memory_item_written", agent_id=agent_id, kind=kind)
        else:
            log.warning(
                "agent_memory_write_failed",
                status=resp.status_code,
                body=resp.text[:200],
            )
    except Exception as exc:
        log.warning("agent_memory_write_error", error=str(exc))


async def append_memory_event(
    supabase_url: str,
    service_role_key: str,
    agent_id: str,
    event_kind: str,
    payload: dict[str, Any] | None = None,
    scope: str = "global",
    source_issue_id: str | None = None,
    source_run_id: str | None = None,
) -> None:
    """Append a run event (append-only; use for status changes, decisions, blockers)."""
    if not supabase_url or not service_role_key:
        return

    body = {
        "agent_id": agent_id,
        "scope": scope,
        "event_kind": event_kind,
        "payload": payload,
        "source_issue_id": source_issue_id,
        "source_run_id": source_run_id,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{supabase_url}/rest/v1/agent_memory_events",
                headers={**_headers(service_role_key), "Prefer": "return=minimal"},
                json=body,
            )
        if resp.status_code not in (200, 201):
            log.warning(
                "agent_memory_event_failed",
                status=resp.status_code,
                body=resp.text[:200],
            )
    except Exception as exc:
        log.warning("agent_memory_event_error", error=str(exc))


async def write_snapshot(
    supabase_url: str,
    service_role_key: str,
    agent_id: str,
    summary: str,
    scope: str = "global",
    items_json: dict[str, Any] | None = None,
    source_run_id: str | None = None,
) -> None:
    """Persist a session snapshot (compacted memory for fast reload next run)."""
    if not supabase_url or not service_role_key:
        return

    body = {
        "agent_id": agent_id,
        "scope": scope,
        "summary": summary,
        "items_json": items_json,
        "source_run_id": source_run_id,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{supabase_url}/rest/v1/agent_memory_snapshots",
                headers={**_headers(service_role_key), "Prefer": "return=minimal"},
                json=body,
            )
        if resp.status_code not in (200, 201):
            log.warning(
                "agent_memory_snapshot_failed",
                status=resp.status_code,
                body=resp.text[:200],
            )
        else:
            log.debug("agent_memory_snapshot_written", agent_id=agent_id, scope=scope)
    except Exception as exc:
        log.warning("agent_memory_snapshot_error", error=str(exc))
