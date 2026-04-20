"""REST endpoint serving canonical GridSignal data to the optimization engine.

Provides:
  GET /grid-signals            — paginated list, filterable by type / location / source
  GET /grid-signals/latest     — one most-recent signal per (signal_type, location_eic)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db

router = APIRouter(prefix="/grid-signals", tags=["grid-signals"])

_VALID_SIGNAL_TYPES = frozenset(
    {"IMBALANCE_PRICE", "TARIFF", "LOAD", "CAPACITY", "CONGESTION", "FREQUENCY", "GENERATION"}
)
_VALID_SOURCES = frozenset({"entso-e", "swissgrid", "ewz", "bkw", "elcom"})
_VALID_QUALITY = frozenset({"measured", "estimated", "forecast"})


# ── Response models ────────────────────────────────────────────────────────────

class GridSignalResponse(BaseModel):
    timestamp: datetime
    dso_id: str
    signal_type: str
    value: float
    unit: str
    location_eic: str
    source: str
    quality: str
    resolution: Optional[str] = None
    period_end: Optional[datetime] = None
    meta: Optional[dict] = None

    model_config = {"from_attributes": True}


class GridSignalsPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[GridSignalResponse]


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("", response_model=GridSignalsPage, summary="List grid signals")
async def list_grid_signals(
    db: Annotated[AsyncSession, Depends(get_db)],
    signal_type: Optional[str] = Query(
        default=None,
        description="Filter by signal type: IMBALANCE_PRICE | TARIFF | LOAD | CAPACITY | CONGESTION | FREQUENCY | GENERATION",
    ),
    location_eic: Optional[str] = Query(
        default=None,
        description="Filter by ENTSO-E location EIC code, e.g. 10YCH-SWISSGRIDC",
    ),
    source: Optional[str] = Query(
        default=None,
        description="Filter by source: entso-e | swissgrid | ewz | bkw | elcom",
    ),
    quality: Optional[str] = Query(
        default=None,
        description="Filter by quality: measured | estimated | forecast",
    ),
    from_ts: Optional[str] = Query(
        alias="from",
        default=None,
        description="ISO 8601 start timestamp (inclusive), defaults to 24 h ago",
    ),
    to_ts: Optional[str] = Query(
        alias="to",
        default=None,
        description="ISO 8601 end timestamp (inclusive), defaults to now",
    ),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> GridSignalsPage:
    """Return paginated GridSignals, filtered by type and/or location.

    Optimised for the KAMA optimization engine: fetch the latest imbalance
    prices for Switzerland with `signal_type=IMBALANCE_PRICE&location_eic=10YCH-SWISSGRIDC`.
    """
    now = datetime.now(timezone.utc)
    ts_from = from_ts or (now.isoformat().replace("+00:00", "Z"))
    ts_to = to_ts or now.isoformat().replace("+00:00", "Z")

    # Build dynamic WHERE clauses using named parameters (SQL injection safe)
    filters: list[str] = ["timestamp BETWEEN :from_ts AND :to_ts"]
    params: dict = {"from_ts": ts_from, "to_ts": ts_to, "limit": limit, "offset": offset}

    if signal_type and signal_type in _VALID_SIGNAL_TYPES:
        filters.append("signal_type = :signal_type")
        params["signal_type"] = signal_type

    if location_eic:
        filters.append("location_eic = :location_eic")
        params["location_eic"] = location_eic

    if source and source in _VALID_SOURCES:
        filters.append("source = :source")
        params["source"] = source

    if quality and quality in _VALID_QUALITY:
        filters.append("quality = :quality")
        params["quality"] = quality

    where = " AND ".join(filters)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM grid_signals WHERE {where}"),
        params,
    )
    total: int = count_result.scalar_one()

    data_result = await db.execute(
        text(f"""
            SELECT timestamp, dso_id, signal_type, value, unit,
                   location_eic, source, quality, resolution, period_end, meta
            FROM grid_signals
            WHERE {where}
            ORDER BY timestamp DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    )
    rows = data_result.mappings().all()

    return GridSignalsPage(
        total=total,
        limit=limit,
        offset=offset,
        items=[GridSignalResponse.model_validate(dict(r)) for r in rows],
    )


@router.get(
    "/latest",
    response_model=list[GridSignalResponse],
    summary="Latest signal per type and location",
)
async def get_latest_signals(
    db: Annotated[AsyncSession, Depends(get_db)],
    signal_type: Optional[str] = Query(default=None),
    location_eic: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None),
) -> list[GridSignalResponse]:
    """Return the single most-recent GridSignal for each (signal_type, location_eic) combination.

    Useful for the optimization engine to get a snapshot of current grid conditions.
    """
    filters: list[str] = []
    params: dict = {}

    if signal_type and signal_type in _VALID_SIGNAL_TYPES:
        filters.append("signal_type = :signal_type")
        params["signal_type"] = signal_type

    if location_eic:
        filters.append("location_eic = :location_eic")
        params["location_eic"] = location_eic

    if source and source in _VALID_SOURCES:
        filters.append("source = :source")
        params["source"] = source

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    result = await db.execute(
        text(f"""
            SELECT DISTINCT ON (signal_type, location_eic)
                timestamp, dso_id, signal_type, value, unit,
                location_eic, source, quality, resolution, period_end, meta
            FROM grid_signals
            {where}
            ORDER BY signal_type, location_eic, timestamp DESC
        """),
        params,
    )
    rows = result.mappings().all()
    return [GridSignalResponse.model_validate(dict(r)) for r in rows]
