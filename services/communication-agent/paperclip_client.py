"""Communication Agent — Paperclip issue creation for internal structured tasks."""
from __future__ import annotations

import httpx
import structlog

from config import settings
from models import InternalTaskRequest

log = structlog.get_logger()


async def create_internal_task(req: InternalTaskRequest) -> str | None:
    """Create a Paperclip issue for a structured internal task. Returns issue id or None."""
    if not settings.paperclip_api_key or not settings.paperclip_company_id:
        log.warning("paperclip_not_configured")
        return None

    description = (
        f"**Auslöser:** {req.trigger}\n\n"
        f"**Verantwortlicher:** {req.responsible}\n\n"
        f"**Ziel:** {req.goal}\n\n"
        f"**Erwartetes Ergebnis:** {req.expected_result}\n\n"
        + (f"**Deadline:** {req.deadline_iso}\n\n" if req.deadline_iso else "")
        + (
            f"**Kontext:**\n```json\n{req.context}\n```\n"
            if req.context
            else ""
        )
    )

    payload: dict = {
        "title": req.goal,
        "description": description,
        "priority": req.priority,
        "status": "todo",
    }
    if settings.paperclip_default_project_id:
        payload["projectId"] = settings.paperclip_default_project_id
    if settings.paperclip_default_goal_id:
        payload["goalId"] = settings.paperclip_default_goal_id

    headers = {
        "Authorization": f"Bearer {settings.paperclip_api_key}",
        "Content-Type": "application/json",
    }
    url = f"{settings.paperclip_api_url}/api/companies/{settings.paperclip_company_id}/issues"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        issue_id = resp.json().get("id")
        log.info("internal_task_created", issue_id=issue_id, goal=req.goal)
        return issue_id
    except Exception as exc:
        log.error("paperclip_create_error", error=str(exc), goal=req.goal)
        return None
