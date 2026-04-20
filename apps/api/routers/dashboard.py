"""
Reporting Dashboard — Roman's live business overview
=====================================================
Provides three primary views + one summary endpoint:

  GET /dashboard/anfragen   — Open AFs with Hot/Warm/Cold segmentation
  GET /dashboard/pipeline   — Auftrags pipeline (Solar vs. BESS)
  GET /dashboard/bess       — BESS Feldbestand (field inventory)
  GET /dashboard/summary    — Full overview for <2-min morning check
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ── Response models ────────────────────────────────────────────────────────────

class AnfragenStats(BaseModel):
    total_open: int
    hot: int
    warm: int
    cold: int
    new_last_7d: int
    estimated_pipeline_chf: float
    by_type: dict[str, int]


class AnfrageRow(BaseModel):
    id: UUID
    kama_net_id: str
    title: str
    customer_name: str
    project_type: str
    status: str
    temperature: str
    estimated_value_chf: Optional[float]
    last_contact_at: Optional[datetime]
    expected_close_date: Optional[date]
    assigned_to: Optional[str]
    age_days: int


class AnfragenResponse(BaseModel):
    stats: AnfragenStats
    anfragen: list[AnfrageRow]
    as_of: datetime


class PipelineStats(BaseModel):
    total_active: int
    total_value_chf: float
    solar_count: int
    solar_value_chf: float
    bess_count: int
    bess_value_chf: float
    by_status: dict[str, int]


class AuftragRow(BaseModel):
    id: UUID
    kama_net_id: str
    title: str
    customer_name: str
    project_type: str
    status: str
    contract_value_chf: Optional[float]
    system_size_kwp: Optional[float]
    expected_completion_date: Optional[date]
    assigned_to: Optional[str]
    days_to_completion: Optional[int]


class PipelineResponse(BaseModel):
    stats: PipelineStats
    auftraege: list[AuftragRow]
    as_of: datetime


class BessRow(BaseModel):
    id: UUID
    name: str
    customer_name: str
    municipality: Optional[str]
    status: str
    capacity_kwh: float
    power_kw: float
    manufacturer: Optional[str]
    model: Optional[str]
    ibn_planned_date: Optional[date]
    ibn_actual_date: Optional[date]
    warranty_until: Optional[date]
    has_live_monitoring: bool
    current_soc_pct: Optional[float]
    notes: Optional[str]


class BessStats(BaseModel):
    total: int
    operational: int
    commissioning: int
    maintenance: int
    offline: int
    total_capacity_kwh: float
    total_power_kw: float
    open_ibn_count: int


class BessResponse(BaseModel):
    stats: BessStats
    installations: list[BessRow]
    as_of: datetime


class DashboardSummary(BaseModel):
    as_of: datetime
    anfragen: AnfragenStats
    pipeline: PipelineStats
    bess: BessStats


# ── Anfragen ───────────────────────────────────────────────────────────────────

@router.get("/anfragen", response_model=AnfragenResponse)
async def get_anfragen(
    db: AsyncSession = Depends(get_db),
    include_won_lost: bool = False,
):
    """
    Open AFs (Anfragen) with Hot/Warm/Cold temperature segmentation.

    Temperature rules (re-applied at query time from last_contact_at):
      hot  — last contact ≤ 7d AND status in (qualified, quoted)
      warm — last contact ≤ 30d
      cold — last contact > 30d or never contacted
    """
    status_filter = (
        "status NOT IN ('won', 'lost', 'cancelled')"
        if not include_won_lost
        else "TRUE"
    )

    result = await db.execute(
        text(f"""
            SELECT
                id,
                kama_net_id,
                title,
                customer_name,
                project_type,
                status,
                -- Re-derive temperature live so it reflects current time
                CASE
                    WHEN last_contact_at >= now() - INTERVAL '7 days'
                         AND status IN ('qualified', 'quoted') THEN 'hot'
                    WHEN last_contact_at >= now() - INTERVAL '30 days' THEN 'warm'
                    ELSE 'cold'
                END AS temperature,
                estimated_value_chf,
                last_contact_at,
                expected_close_date,
                assigned_to,
                EXTRACT(DAY FROM now() - created_at)::int AS age_days
            FROM crm_anfragen
            WHERE {status_filter}
            ORDER BY
                CASE
                    WHEN last_contact_at >= now() - INTERVAL '7 days'
                         AND status IN ('qualified', 'quoted') THEN 0
                    WHEN last_contact_at >= now() - INTERVAL '30 days' THEN 1
                    ELSE 2
                END,
                estimated_value_chf DESC NULLS LAST
        """),
    )
    rows = result.mappings().all()

    anfragen = [
        AnfrageRow(
            id=r["id"],
            kama_net_id=r["kama_net_id"],
            title=r["title"],
            customer_name=r["customer_name"],
            project_type=r["project_type"],
            status=r["status"],
            temperature=r["temperature"],
            estimated_value_chf=r["estimated_value_chf"],
            last_contact_at=r["last_contact_at"],
            expected_close_date=r["expected_close_date"],
            assigned_to=r["assigned_to"],
            age_days=r["age_days"] or 0,
        )
        for r in rows
    ]

    hot = sum(1 for a in anfragen if a.temperature == "hot")
    warm = sum(1 for a in anfragen if a.temperature == "warm")
    cold = sum(1 for a in anfragen if a.temperature == "cold")

    # Count AFs created in the last 7 days
    new_result = await db.execute(
        text("SELECT COUNT(*) AS cnt FROM crm_anfragen WHERE created_at >= now() - INTERVAL '7 days'")
    )
    new_last_7d = new_result.scalar() or 0

    by_type: dict[str, int] = {}
    pipeline_chf = 0.0
    for a in anfragen:
        by_type[a.project_type] = by_type.get(a.project_type, 0) + 1
        if a.estimated_value_chf:
            pipeline_chf += a.estimated_value_chf

    stats = AnfragenStats(
        total_open=len(anfragen),
        hot=hot,
        warm=warm,
        cold=cold,
        new_last_7d=new_last_7d,
        estimated_pipeline_chf=round(pipeline_chf, 2),
        by_type=by_type,
    )

    return AnfragenResponse(
        stats=stats,
        anfragen=anfragen,
        as_of=datetime.now(timezone.utc),
    )


# ── Pipeline (Aufträge) ────────────────────────────────────────────────────────

@router.get("/pipeline", response_model=PipelineResponse)
async def get_pipeline(
    db: AsyncSession = Depends(get_db),
    include_completed: bool = False,
):
    """
    Active order pipeline broken down by Solar vs. BESS.
    Excludes cancelled orders. Optionally includes completed orders.
    """
    status_filter = (
        "status NOT IN ('cancelled', 'completed')"
        if not include_completed
        else "status != 'cancelled'"
    )

    result = await db.execute(
        text(f"""
            SELECT
                id,
                kama_net_id,
                title,
                customer_name,
                project_type,
                status,
                contract_value_chf,
                system_size_kwp,
                expected_completion_date,
                assigned_to,
                CASE
                    WHEN expected_completion_date IS NOT NULL
                    THEN (expected_completion_date - CURRENT_DATE)
                    ELSE NULL
                END AS days_to_completion
            FROM crm_auftraege
            WHERE {status_filter}
            ORDER BY
                CASE status
                    WHEN 'commissioning' THEN 0
                    WHEN 'installation' THEN 1
                    WHEN 'ordered'      THEN 2
                    WHEN 'planning'     THEN 3
                    ELSE 4
                END,
                expected_completion_date ASC NULLS LAST
        """),
    )
    rows = result.mappings().all()

    auftraege = [
        AuftragRow(
            id=r["id"],
            kama_net_id=r["kama_net_id"],
            title=r["title"],
            customer_name=r["customer_name"],
            project_type=r["project_type"],
            status=r["status"],
            contract_value_chf=r["contract_value_chf"],
            system_size_kwp=r["system_size_kwp"],
            expected_completion_date=r["expected_completion_date"],
            assigned_to=r["assigned_to"],
            days_to_completion=r["days_to_completion"],
        )
        for r in rows
    ]

    solar = [a for a in auftraege if a.project_type == "solar"]
    bess = [a for a in auftraege if a.project_type == "bess"]

    solar_value = sum(a.contract_value_chf or 0 for a in solar)
    bess_value = sum(a.contract_value_chf or 0 for a in bess)

    by_status: dict[str, int] = {}
    for a in auftraege:
        by_status[a.status] = by_status.get(a.status, 0) + 1

    stats = PipelineStats(
        total_active=len(auftraege),
        total_value_chf=round(solar_value + bess_value, 2),
        solar_count=len(solar),
        solar_value_chf=round(solar_value, 2),
        bess_count=len(bess),
        bess_value_chf=round(bess_value, 2),
        by_status=by_status,
    )

    return PipelineResponse(
        stats=stats,
        auftraege=auftraege,
        as_of=datetime.now(timezone.utc),
    )


# ── BESS Feldbestand ───────────────────────────────────────────────────────────

@router.get("/bess", response_model=BessResponse)
async def get_bess_inventory(
    db: AsyncSession = Depends(get_db),
):
    """
    BESS field inventory: all installed/commissioning systems with live SoC
    for units already connected to the monitoring platform.
    """
    result = await db.execute(
        text("""
            SELECT
                b.id,
                b.name,
                b.customer_name,
                b.municipality,
                b.status,
                b.capacity_kwh,
                b.power_kw,
                b.manufacturer,
                b.model,
                b.ibn_planned_date,
                b.ibn_actual_date,
                b.warranty_until,
                b.notes,
                b.site_id IS NOT NULL AS has_live_monitoring,
                -- Latest SoC from telemetry if site is linked
                (
                    SELECT AVG(t.soc_pct)
                    FROM telemetry t
                    WHERE t.site_id = b.site_id
                      AND t.device_type = 'bess'
                      AND t.soc_pct IS NOT NULL
                      AND t.time > now() - INTERVAL '15 minutes'
                ) AS current_soc_pct
            FROM bess_installations b
            WHERE b.status != 'decommissioned'
            ORDER BY
                CASE b.status
                    WHEN 'operational'   THEN 0
                    WHEN 'commissioning' THEN 1
                    WHEN 'maintenance'   THEN 2
                    WHEN 'offline'       THEN 3
                    ELSE 4
                END,
                b.name ASC
        """),
    )
    rows = result.mappings().all()

    installations = [
        BessRow(
            id=r["id"],
            name=r["name"],
            customer_name=r["customer_name"],
            municipality=r["municipality"],
            status=r["status"],
            capacity_kwh=r["capacity_kwh"],
            power_kw=r["power_kw"],
            manufacturer=r["manufacturer"],
            model=r["model"],
            ibn_planned_date=r["ibn_planned_date"],
            ibn_actual_date=r["ibn_actual_date"],
            warranty_until=r["warranty_until"],
            has_live_monitoring=r["has_live_monitoring"],
            current_soc_pct=(
                round(r["current_soc_pct"], 1) if r["current_soc_pct"] is not None else None
            ),
            notes=r["notes"],
        )
        for r in rows
    ]

    today = date.today()
    open_ibn = sum(
        1 for i in installations
        if i.status == "commissioning"
        and i.ibn_planned_date is not None
        and i.ibn_actual_date is None
    )

    stats = BessStats(
        total=len(installations),
        operational=sum(1 for i in installations if i.status == "operational"),
        commissioning=sum(1 for i in installations if i.status == "commissioning"),
        maintenance=sum(1 for i in installations if i.status == "maintenance"),
        offline=sum(1 for i in installations if i.status == "offline"),
        total_capacity_kwh=round(sum(i.capacity_kwh for i in installations), 1),
        total_power_kw=round(sum(i.power_kw for i in installations), 1),
        open_ibn_count=open_ibn,
    )

    return BessResponse(
        stats=stats,
        installations=installations,
        as_of=datetime.now(timezone.utc),
    )


# ── Summary (Roman's morning view) ────────────────────────────────────────────

@router.get("/summary", response_model=DashboardSummary)
async def get_summary(
    db: AsyncSession = Depends(get_db),
):
    """
    Single-call overview for Roman's daily <2-minute check.
    Returns aggregate stats for Anfragen, Pipeline, and BESS — no row detail.
    """
    now = datetime.now(timezone.utc)

    # Anfragen stats
    af_result = await db.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE status NOT IN ('won','lost','cancelled'))                                    AS total_open,
                COUNT(*) FILTER (WHERE status NOT IN ('won','lost','cancelled')
                                   AND last_contact_at >= now() - INTERVAL '7 days'
                                   AND status IN ('qualified','quoted'))                                            AS hot,
                COUNT(*) FILTER (WHERE status NOT IN ('won','lost','cancelled')
                                   AND last_contact_at >= now() - INTERVAL '30 days'
                                   AND NOT (last_contact_at >= now() - INTERVAL '7 days'
                                            AND status IN ('qualified','quoted')))                                  AS warm,
                COUNT(*) FILTER (WHERE status NOT IN ('won','lost','cancelled')
                                   AND (last_contact_at IS NULL
                                        OR last_contact_at < now() - INTERVAL '30 days'))                          AS cold,
                COUNT(*) FILTER (WHERE created_at >= now() - INTERVAL '7 days')                                    AS new_last_7d,
                COALESCE(SUM(estimated_value_chf) FILTER (
                    WHERE status NOT IN ('won','lost','cancelled')), 0)                                             AS pipeline_chf,
                COUNT(*) FILTER (WHERE status NOT IN ('won','lost','cancelled')
                                   AND project_type = 'solar')                                                     AS solar_count,
                COUNT(*) FILTER (WHERE status NOT IN ('won','lost','cancelled')
                                   AND project_type = 'bess')                                                      AS bess_count,
                COUNT(*) FILTER (WHERE status NOT IN ('won','lost','cancelled')
                                   AND project_type = 'vzev')                                                      AS vzev_count,
                COUNT(*) FILTER (WHERE status NOT IN ('won','lost','cancelled')
                                   AND project_type = 'combined')                                                  AS combined_count
            FROM crm_anfragen
        """),
    )
    af = af_result.mappings().one()

    # Pipeline stats
    pl_result = await db.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE status NOT IN ('cancelled','completed'))          AS total_active,
                COALESCE(SUM(contract_value_chf) FILTER (
                    WHERE status NOT IN ('cancelled','completed')), 0)                   AS total_value_chf,
                COUNT(*) FILTER (WHERE status NOT IN ('cancelled','completed')
                                   AND project_type = 'solar')                          AS solar_count,
                COALESCE(SUM(contract_value_chf) FILTER (
                    WHERE status NOT IN ('cancelled','completed')
                      AND project_type = 'solar'), 0)                                   AS solar_value_chf,
                COUNT(*) FILTER (WHERE status NOT IN ('cancelled','completed')
                                   AND project_type = 'bess')                           AS bess_count,
                COALESCE(SUM(contract_value_chf) FILTER (
                    WHERE status NOT IN ('cancelled','completed')
                      AND project_type = 'bess'), 0)                                    AS bess_value_chf,
                COUNT(*) FILTER (WHERE status = 'commissioning')                         AS commissioning_count,
                COUNT(*) FILTER (WHERE status = 'installation')                          AS installation_count,
                COUNT(*) FILTER (WHERE status = 'ordered')                               AS ordered_count,
                COUNT(*) FILTER (WHERE status = 'planning')                              AS planning_count
            FROM crm_auftraege
        """),
    )
    pl = pl_result.mappings().one()

    # BESS stats
    bess_result = await db.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE status != 'decommissioned')          AS total,
                COUNT(*) FILTER (WHERE status = 'operational')              AS operational,
                COUNT(*) FILTER (WHERE status = 'commissioning')            AS commissioning,
                COUNT(*) FILTER (WHERE status = 'maintenance')              AS maintenance,
                COUNT(*) FILTER (WHERE status = 'offline')                  AS offline,
                COALESCE(SUM(capacity_kwh) FILTER (
                    WHERE status != 'decommissioned'), 0)                   AS total_capacity_kwh,
                COALESCE(SUM(power_kw) FILTER (
                    WHERE status != 'decommissioned'), 0)                   AS total_power_kw,
                COUNT(*) FILTER (
                    WHERE status = 'commissioning'
                      AND ibn_planned_date IS NOT NULL
                      AND ibn_actual_date IS NULL)                          AS open_ibn_count
            FROM bess_installations
        """),
    )
    bess = bess_result.mappings().one()

    return DashboardSummary(
        as_of=now,
        anfragen=AnfragenStats(
            total_open=af["total_open"] or 0,
            hot=af["hot"] or 0,
            warm=af["warm"] or 0,
            cold=af["cold"] or 0,
            new_last_7d=af["new_last_7d"] or 0,
            estimated_pipeline_chf=round(float(af["pipeline_chf"] or 0), 2),
            by_type={
                "solar": af["solar_count"] or 0,
                "bess": af["bess_count"] or 0,
                "vzev": af["vzev_count"] or 0,
                "combined": af["combined_count"] or 0,
            },
        ),
        pipeline=PipelineStats(
            total_active=pl["total_active"] or 0,
            total_value_chf=round(float(pl["total_value_chf"] or 0), 2),
            solar_count=pl["solar_count"] or 0,
            solar_value_chf=round(float(pl["solar_value_chf"] or 0), 2),
            bess_count=pl["bess_count"] or 0,
            bess_value_chf=round(float(pl["bess_value_chf"] or 0), 2),
            by_status={
                "commissioning": pl["commissioning_count"] or 0,
                "installation": pl["installation_count"] or 0,
                "ordered": pl["ordered_count"] or 0,
                "planning": pl["planning_count"] or 0,
            },
        ),
        bess=BessStats(
            total=bess["total"] or 0,
            operational=bess["operational"] or 0,
            commissioning=bess["commissioning"] or 0,
            maintenance=bess["maintenance"] or 0,
            offline=bess["offline"] or 0,
            total_capacity_kwh=round(float(bess["total_capacity_kwh"] or 0), 1),
            total_power_kw=round(float(bess["total_power_kw"] or 0), 1),
            open_ibn_count=bess["open_ibn_count"] or 0,
        ),
    )
