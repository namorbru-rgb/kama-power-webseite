"""Montage Agent — resource & calendar scheduling."""
from __future__ import annotations

import httpx
import structlog
from datetime import date, timedelta

from config import settings
from models import Technician

log = structlog.get_logger()

_FALLBACK_TECHNICIANS: list[Technician] = [
    Technician(id="tech-1", name="Monteur A", skills=["solar", "bess"]),
    Technician(id="tech-2", name="Monteur B", skills=["solar", "vzev"]),
]


async def fetch_technicians() -> list[Technician]:
    """Load technicians from KAMA-net app_technicians table."""
    if not settings.kama_net_api_key:
        log.warning("kama_net_api_key_missing", fallback=True)
        return _FALLBACK_TECHNICIANS

    url = f"{settings.kama_net_url}/rest/v1/{settings.kama_net_technicians_table}"
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
        log.warning("technicians_fetch_failed", error=str(exc), fallback=True)
        return _FALLBACK_TECHNICIANS

    technicians = []
    for entry in data:
        technicians.append(
            Technician(
                id=entry.get("id", ""),
                name=entry.get("name", "Unknown"),
                telegram_chat_id=entry.get("telegram_chat_id"),
                phone=entry.get("phone"),
                skills=entry.get("skills", []) or [],
                blocked_dates=entry.get("blocked_dates", []) or [],
            )
        )
    log.info("technicians_loaded", count=len(technicians))
    return technicians


def _is_available(tech: Technician, candidate_date: date) -> bool:
    """Return True if the technician has no block on candidate_date."""
    blocked = {d[:10] for d in tech.blocked_dates}
    return candidate_date.isoformat() not in blocked


def assign_technician(
    technicians: list[Technician],
    project_type: str,
    horizon_days: int = 14,
    strategy: str = "earliest_available",
) -> tuple[Technician | None, date | None]:
    """
    Find the best technician and earliest available date for a given project type.

    Returns (technician, planned_date) or (None, None) if no match found.
    """
    eligible = [t for t in technicians if project_type in t.skills or not t.skills]
    if not eligible:
        eligible = technicians  # fallback to any technician

    today = date.today()
    # Skip weekends, look up to horizon_days ahead
    candidate_dates = [
        today + timedelta(days=d)
        for d in range(1, horizon_days + 1)
        if (today + timedelta(days=d)).weekday() < 5  # Mon–Fri
    ]

    if strategy == "round_robin":
        # Sort alphabetically by ID to ensure consistent round-robin order
        eligible.sort(key=lambda t: t.id)

    for candidate_date in candidate_dates:
        for tech in eligible:
            if _is_available(tech, candidate_date):
                log.info(
                    "technician_assigned",
                    technician=tech.name,
                    date=candidate_date.isoformat(),
                    project_type=project_type,
                )
                return tech, candidate_date

    log.warning("no_technician_available", project_type=project_type)
    return None, None
