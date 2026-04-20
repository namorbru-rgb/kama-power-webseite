"""
VZEV/LEG billing API
====================
Exposes community setup, membership management, and billing period queries.
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db

router = APIRouter(prefix="/vzev", tags=["vzev"])


# ── Pydantic models ────────────────────────────────────────────────────────────

class CommunityCreate(BaseModel):
    name: str
    community_type: str = "vzev"
    dso_name: str
    dso_eic: str | None = None
    grid_zone_id: str | None = None
    producer_site_id: UUID
    municipality_bfs: str | None = None
    feed_in_tariff_chf_kwh: float = 0.11
    draw_tariff_chf_kwh: float = 0.22


class MembershipCreate(BaseModel):
    site_id: UUID
    participant_name: str
    allocation_share: float = 0.0
    allocation_method: str = "proportional"
    member_from: date
    member_until: date | None = None
    billing_email: str | None = None


class BillingSummary(BaseModel):
    billing_period_id: UUID
    community_id: UUID
    period_start: date
    period_end: date
    total_production_kwh: float
    total_feed_in_kwh: float
    total_draw_kwh: float
    status: str
    invoice_lines: list[dict]


# ── Community CRUD ─────────────────────────────────────────────────────────────

@router.post("/communities", status_code=201)
async def create_community(
    body: CommunityCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        text("""
            INSERT INTO vzev_communities
                (name, community_type, dso_name, dso_eic, grid_zone_id,
                 producer_site_id, municipality_bfs,
                 feed_in_tariff_chf_kwh, draw_tariff_chf_kwh)
            VALUES
                (:name, :community_type, :dso_name, :dso_eic, :grid_zone_id,
                 :producer_site_id, :municipality_bfs,
                 :feed_in_tariff_chf_kwh, :draw_tariff_chf_kwh)
            RETURNING id
        """),
        body.model_dump(),
    )
    await db.commit()
    row = result.mappings().one()
    return {"id": row["id"]}


@router.get("/communities/{community_id}")
async def get_community(
    community_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        text("SELECT * FROM vzev_communities WHERE id = :id"),
        {"id": str(community_id)},
    )
    row = result.mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Community not found")
    return dict(row)


# ── Membership CRUD ────────────────────────────────────────────────────────────

@router.post("/communities/{community_id}/members", status_code=201)
async def add_member(
    community_id: UUID,
    body: MembershipCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        text("""
            INSERT INTO vzev_memberships
                (community_id, site_id, participant_name, allocation_share,
                 allocation_method, member_from, member_until, billing_email)
            VALUES
                (:community_id, :site_id, :participant_name, :allocation_share,
                 :allocation_method, :member_from, :member_until, :billing_email)
            RETURNING id
        """),
        {
            "community_id": str(community_id),
            **body.model_dump(),
            "site_id": str(body.site_id),
        },
    )
    await db.commit()
    row = result.mappings().one()
    return {"id": row["id"]}


@router.get("/communities/{community_id}/members")
async def list_members(
    community_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        text("""
            SELECT m.*, s.name AS site_name, s.address AS site_address
            FROM vzev_memberships m
            JOIN sites s ON s.id = m.site_id
            WHERE m.community_id = :community_id
            ORDER BY m.participant_name
        """),
        {"community_id": str(community_id)},
    )
    return [dict(r) for r in result.mappings().all()]


# ── Billing ────────────────────────────────────────────────────────────────────

@router.get("/communities/{community_id}/billing/{year_month}", response_model=BillingSummary)
async def get_billing_period(
    community_id: UUID,
    year_month: str,   # YYYY-MM
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Retrieve a finalized billing period with per-participant invoice lines."""
    try:
        year, month = map(int, year_month.split("-"))
        period_start = date(year, month, 1)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="year_month must be YYYY-MM")

    result = await db.execute(
        text("""
            SELECT bp.*, row_to_json(bp.*) AS _raw
            FROM vzev_billing_periods bp
            WHERE bp.community_id = :community_id
              AND bp.period_start = :period_start
        """),
        {"community_id": str(community_id), "period_start": period_start},
    )
    bp = result.mappings().one_or_none()
    if not bp:
        raise HTTPException(status_code=404, detail="Billing period not found")

    lines_result = await db.execute(
        text("""
            SELECT
                il.*,
                m.participant_name,
                m.billing_email,
                s.name AS site_name
            FROM vzev_invoice_lines il
            JOIN vzev_memberships m ON m.id = il.membership_id
            JOIN sites s ON s.id = m.site_id
            WHERE il.billing_period_id = :bp_id
            ORDER BY m.participant_name
        """),
        {"bp_id": str(bp["id"])},
    )
    lines = [dict(r) for r in lines_result.mappings().all()]

    return BillingSummary(
        billing_period_id=bp["id"],
        community_id=community_id,
        period_start=bp["period_start"],
        period_end=bp["period_end"],
        total_production_kwh=bp["total_production_kwh"],
        total_feed_in_kwh=bp["total_feed_in_kwh"],
        total_draw_kwh=bp["total_draw_kwh"],
        status=bp["status"],
        invoice_lines=lines,
    )


@router.get("/communities/{community_id}/billing")
async def list_billing_periods(
    community_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """List all billing periods for a community."""
    result = await db.execute(
        text("""
            SELECT id, period_start, period_end, status,
                   total_production_kwh, total_feed_in_kwh, total_draw_kwh,
                   finalized_at, dso_reported_at
            FROM vzev_billing_periods
            WHERE community_id = :community_id
            ORDER BY period_start DESC
        """),
        {"community_id": str(community_id)},
    )
    return [dict(r) for r in result.mappings().all()]
