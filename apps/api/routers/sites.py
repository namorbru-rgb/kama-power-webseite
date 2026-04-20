from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models import (
    CurrentReading,
    DailySummary,
    Device,
    Site,
    TrendPoint,
    TrendResponse,
)

router = APIRouter(prefix="/sites", tags=["sites"])

# Swiss average grid emission factor (gCO₂eq/kWh) — source: SFOE 2023
SWISS_GRID_CO2_G_PER_KWH = 28.0
# Typical Swiss feed-in tariff CHF/kWh (KEV/EVS indicative)
FEED_IN_TARIFF_CHF_KWH = 0.11


# ── Current live reading ──────────────────────────────────────────────────────

@router.get("/{site_id}/current", response_model=CurrentReading)
async def get_current(
    site_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Latest live snapshot for a site — aggregated across all devices."""
    # Grab the most recent reading per direction for this site within last 5 min
    result = await db.execute(
        text("""
            SELECT
                direction,
                SUM(power_w) AS total_w,
                AVG(soc_pct) AS avg_soc,
                MAX(time)    AS latest_time
            FROM telemetry
            WHERE site_id = :site_id
              AND time > now() - INTERVAL '5 minutes'
            GROUP BY direction
        """),
        {"site_id": str(site_id)},
    )
    rows = result.mappings().all()

    if not rows:
        raise HTTPException(status_code=404, detail="No recent data for this site")

    by_dir: dict[str, float] = {r["direction"]: r["total_w"] or 0.0 for r in rows}
    soc_row = next((r for r in rows if r["avg_soc"] is not None), None)
    latest_time = max(r["latest_time"] for r in rows)

    production = by_dir.get("production", 0.0)
    consumption = by_dir.get("consumption", 0.0)
    feed_in = by_dir.get("feed_in", 0.0)
    draw = by_dir.get("draw", 0.0)
    bess_power = by_dir.get("charge", 0.0) - by_dir.get("discharge", 0.0)

    self_suff = (
        min(production, consumption) / consumption * 100
        if consumption > 0
        else 0.0
    )

    return CurrentReading(
        site_id=site_id,
        recorded_at=latest_time,
        production_w=production,
        consumption_w=consumption,
        feed_in_w=feed_in,
        draw_w=draw,
        bess_power_w=bess_power,
        bess_soc_pct=soc_row["avg_soc"] if soc_row else None,
        self_sufficiency_pct=round(self_suff, 1),
    )


# ── Daily summary ─────────────────────────────────────────────────────────────

@router.get("/{site_id}/summary", response_model=DailySummary)
async def get_daily_summary(
    site_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    day: str = Query(default=None, description="YYYY-MM-DD, defaults to today"),
):
    """Today's (or a specific day's) energy totals."""
    if day is None:
        target = date.today().isoformat()
    else:
        target = day

    result = await db.execute(
        text("""
            SELECT
                direction,
                SUM(delta_kwh) AS total_kwh
            FROM telemetry_daily
            WHERE site_id = :site_id
              AND bucket = :day::date
            GROUP BY direction
        """),
        {"site_id": str(site_id), "day": target},
    )
    rows = result.mappings().all()

    by_dir = {r["direction"]: r["total_kwh"] or 0.0 for r in rows}

    production = by_dir.get("production", 0.0)
    consumption = by_dir.get("consumption", 0.0)
    feed_in = by_dir.get("feed_in", 0.0)
    draw = by_dir.get("draw", 0.0)

    self_suff = (
        min(production, consumption) / consumption * 100
        if consumption > 0
        else 0.0
    )
    co2_avoided = production * SWISS_GRID_CO2_G_PER_KWH / 1000  # kg
    revenue = feed_in * FEED_IN_TARIFF_CHF_KWH

    return DailySummary(
        site_id=site_id,
        date=target,
        production_kwh=round(production, 3),
        consumption_kwh=round(consumption, 3),
        feed_in_kwh=round(feed_in, 3),
        draw_kwh=round(draw, 3),
        self_sufficiency_pct=round(self_suff, 1),
        co2_avoided_kg=round(co2_avoided, 2),
        feed_in_revenue_chf=round(revenue, 2),
    )


# ── Historical trend ──────────────────────────────────────────────────────────

@router.get("/{site_id}/trend", response_model=TrendResponse)
async def get_trend(
    site_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    from_: str = Query(alias="from", description="ISO datetime"),
    to: str = Query(default=None, description="ISO datetime, defaults to now"),
    resolution: Literal["15m", "hourly", "daily"] = Query(default="hourly"),
):
    """Time-series energy data for charting."""
    if to is None:
        to = datetime.now(timezone.utc).isoformat()

    table = {
        "15m": "telemetry_15m",
        "hourly": "telemetry_hourly",
        "daily": "telemetry_daily",
    }[resolution]

    result = await db.execute(
        text(f"""
            SELECT
                bucket,
                direction,
                COALESCE(SUM(delta_kwh), 0) AS kwh
            FROM {table}
            WHERE site_id = :site_id
              AND bucket BETWEEN :from_ts AND :to_ts
            GROUP BY bucket, direction
            ORDER BY bucket ASC
        """),
        {"site_id": str(site_id), "from_ts": from_, "to_ts": to},
    )
    rows = result.mappings().all()

    # Pivot by bucket
    buckets: dict[datetime, dict[str, float]] = {}
    for r in rows:
        b = r["bucket"]
        if b not in buckets:
            buckets[b] = {}
        buckets[b][r["direction"]] = r["kwh"]

    points = [
        TrendPoint(
            bucket=b,
            production_kwh=round(v.get("production", 0.0), 3),
            consumption_kwh=round(v.get("consumption", 0.0), 3),
            feed_in_kwh=round(v.get("feed_in", 0.0), 3),
            draw_kwh=round(v.get("draw", 0.0), 3),
        )
        for b, v in sorted(buckets.items())
    ]

    return TrendResponse(site_id=site_id, resolution=resolution, points=points)


# ── Device list ───────────────────────────────────────────────────────────────

@router.get("/{site_id}/devices", response_model=list[Device])
async def list_devices(
    site_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        text("SELECT * FROM devices WHERE site_id = :site_id AND active = true"),
        {"site_id": str(site_id)},
    )
    return [Device.model_validate(dict(r)) for r in result.mappings().all()]


# ── Grid stats ────────────────────────────────────────────────────────────────

@router.get("/{site_id}/grid")
async def get_grid_stats(
    site_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    period: Literal["today", "week", "month"] = "today",
):
    """Grid feed-in and draw totals for the requested period."""
    interval_map = {"today": "1 day", "week": "7 days", "month": "30 days"}
    interval = interval_map[period]

    result = await db.execute(
        text("""
            SELECT direction, COALESCE(SUM(delta_kwh), 0) AS kwh
            FROM telemetry_daily
            WHERE site_id = :site_id
              AND bucket >= now() - :interval::interval
              AND direction IN ('feed_in', 'draw')
            GROUP BY direction
        """),
        {"site_id": str(site_id), "interval": interval},
    )
    rows = {r["direction"]: round(r["kwh"], 3) for r in result.mappings().all()}

    feed_in = rows.get("feed_in", 0.0)
    draw = rows.get("draw", 0.0)

    return {
        "site_id": site_id,
        "period": period,
        "feed_in_kwh": feed_in,
        "draw_kwh": draw,
        "net_kwh": round(feed_in - draw, 3),
        "feed_in_revenue_chf": round(feed_in * FEED_IN_TARIFF_CHF_KWH, 2),
    }
