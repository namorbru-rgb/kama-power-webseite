"""Projekt- & Workflow-Engine — Paperclip REST API client."""
from __future__ import annotations

import structlog
import httpx

from config import settings
from models import PaperclipIssueCreate, PaperclipIssueResponse

log = structlog.get_logger()

# Role → agent_id mapping (resolved at startup if not pre-configured)
_ROLE_AGENT_IDS: dict[str, str] = {}


async def resolve_agent_ids() -> None:
    """Fetch all company agents and build role → agent_id map."""
    global _ROLE_AGENT_IDS

    # Use pre-configured IDs if set
    role_map = {
        "ceo": settings.agent_id_ceo,
        "cto": settings.agent_id_cto,
        "procurement": settings.agent_id_procurement,
        "montage": settings.agent_id_montage,
        "meldewesen": settings.agent_id_meldewesen,
    }
    if all(role_map.values()):
        _ROLE_AGENT_IDS = role_map
        log.info("agent_ids_from_config", roles=list(role_map.keys()))
        return

    # Fallback: fetch agents and match by nameKey
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{settings.paperclip_api_url}/api/companies/{settings.paperclip_company_id}/agents",
            headers={"Authorization": f"Bearer {settings.paperclip_api_key}"},
        )
        resp.raise_for_status()
        agents = resp.json()

    # Map nameKey → id
    namekey_map: dict[str, str] = {a["nameKey"]: a["id"] for a in agents if "nameKey" in a}

    # Role heuristic: match nameKey contains role keyword
    role_keywords = {
        "ceo": ["ceo", "boss", "chief"],
        "cto": ["cto", "tech"],
        "procurement": ["procurement", "beschaffung", "einkauf"],
        "montage": ["montage", "produktion", "installation"],
        "meldewesen": ["meldewesen", "admin", "registration"],
    }

    for role, keywords in role_keywords.items():
        if role_map.get(role):
            _ROLE_AGENT_IDS[role] = role_map[role]
            continue
        for key, agent_id in namekey_map.items():
            if any(kw in key.lower() for kw in keywords):
                _ROLE_AGENT_IDS[role] = agent_id
                break

    log.info("agent_ids_resolved", resolved=_ROLE_AGENT_IDS)


def get_agent_id_for_role(role: str) -> str | None:
    """Return the Paperclip agent ID for a given role, or None."""
    return _ROLE_AGENT_IDS.get(role)


async def create_paperclip_issue(
    issue: PaperclipIssueCreate,
) -> PaperclipIssueResponse:
    """Create a Paperclip issue and return the response."""
    payload = issue.model_dump(exclude_none=True)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{settings.paperclip_api_url}/api/companies/{settings.paperclip_company_id}/issues",
            headers={
                "Authorization": f"Bearer {settings.paperclip_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    result = PaperclipIssueResponse.model_validate(data)
    log.info(
        "paperclip_issue_created",
        id=result.id,
        key=result.identifier,
        title=result.title,
    )
    return result


async def add_comment(issue_id: str, body: str) -> None:
    """Post a markdown comment to a Paperclip issue."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{settings.paperclip_api_url}/api/issues/{issue_id}/comments",
            headers={
                "Authorization": f"Bearer {settings.paperclip_api_key}",
                "Content-Type": "application/json",
            },
            json={"body": body},
        )
        resp.raise_for_status()
