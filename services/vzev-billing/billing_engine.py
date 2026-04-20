"""
KAMA VZEV Billing Engine
========================
Computes 15-minute energy allocations across VZEV community participants and
aggregates them into monthly invoice lines.

Legal basis: EnG Art. 17 (ZEV) / Art. 18 (VZEV), VESE model billing framework.

Flow:
  1. For each 15-min interval in the billing period:
     a. Fetch total community solar production (kWh) from telemetry_15m
        for the producer site.
     b. Fetch each participant's actual consumption (kWh) from their site's
        smart_meter telemetry.
     c. Allocate production proportionally (or by static share) to participants.
     d. Any production surplus → community feed-in to grid.
     e. Any participant shortfall (demand > allocated) → residual grid draw.
     f. Write one vzev_interval_allocations row per participant per interval.
  2. Aggregate interval rows into vzev_invoice_lines per member.
  3. Apply tariffs and compute CHF totals.
  4. Set billing period status to 'finalized'.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Sequence
from uuid import UUID

import asyncpg

from config import settings

logger = logging.getLogger(__name__)


# ─── Domain types ─────────────────────────────────────────────────────────────

@dataclass
class MemberState:
    membership_id: UUID
    site_id: UUID
    allocation_method: str          # 'proportional' | 'static'
    static_share: float             # 0.0–1.0, used only for static method


@dataclass
class IntervalResult:
    membership_id: UUID
    allocated_kwh: float
    grid_draw_kwh: float
    effective_share: float


# ─── Core allocation logic ────────────────────────────────────────────────────

def allocate_interval(
    production_kwh: float,
    consumptions: dict[UUID, float],     # membership_id → measured consumption kWh
    members: list[MemberState],
) -> list[IntervalResult]:
    """
    Allocate community production among participants for one 15-min interval.

    Proportional method: each participant's share equals their fraction of total
    community consumption. If total consumption is zero, fall back to equal share.

    Static method: uses the fixed allocation_share declared in the membership.

    Returns one IntervalResult per member.
    """
    results: list[IntervalResult] = []

    if not members:
        return results

    # Compute effective shares
    shares: dict[UUID, float] = {}
    static_members = [m for m in members if m.allocation_method == "static"]
    prop_members = [m for m in members if m.allocation_method == "proportional"]

    # Static members first: their share is fixed
    static_total = sum(m.static_share for m in static_members)
    for m in static_members:
        shares[m.membership_id] = m.static_share

    # Proportional members share the remaining fraction
    remaining_fraction = max(0.0, 1.0 - static_total)
    prop_consumption_total = sum(
        consumptions.get(m.membership_id, 0.0) for m in prop_members
    )

    for m in prop_members:
        cons = consumptions.get(m.membership_id, 0.0)
        if prop_consumption_total > 0:
            shares[m.membership_id] = remaining_fraction * cons / prop_consumption_total
        else:
            # Fallback: equal split among proportional members
            shares[m.membership_id] = remaining_fraction / len(prop_members) if prop_members else 0.0

    # Apply shares to production
    for m in members:
        share = shares.get(m.membership_id, 0.0)
        allocated = production_kwh * share
        consumed = consumptions.get(m.membership_id, 0.0)

        # Participant can only use what they actually consumed
        allocated = min(allocated, consumed)
        grid_draw = max(0.0, consumed - allocated)

        results.append(IntervalResult(
            membership_id=m.membership_id,
            allocated_kwh=round(allocated, 6),
            grid_draw_kwh=round(grid_draw, 6),
            effective_share=round(share, 6),
        ))

    return results


# ─── Database helpers ─────────────────────────────────────────────────────────

async def fetch_community(conn: asyncpg.Connection, community_id: UUID) -> asyncpg.Record:
    row = await conn.fetchrow(
        "SELECT * FROM vzev_communities WHERE id = $1 AND active = true",
        community_id,
    )
    if not row:
        raise ValueError(f"Community {community_id} not found or inactive")
    return row


async def fetch_active_members(
    conn: asyncpg.Connection,
    community_id: UUID,
    period_start: date,
    period_end: date,
) -> list[MemberState]:
    rows = await conn.fetch(
        """
        SELECT id, site_id, allocation_method, allocation_share
        FROM vzev_memberships
        WHERE community_id = $1
          AND member_from <= $3
          AND (member_until IS NULL OR member_until >= $2)
        ORDER BY id
        """,
        community_id,
        period_start,
        period_end,
    )
    return [
        MemberState(
            membership_id=r["id"],
            site_id=r["site_id"],
            allocation_method=r["allocation_method"],
            static_share=r["allocation_share"],
        )
        for r in rows
    ]


async def fetch_production_kwh(
    conn: asyncpg.Connection,
    producer_site_id: UUID,
    bucket: datetime,
) -> float:
    """Total solar production kWh for the producer site in this 15-min bucket."""
    row = await conn.fetchrow(
        """
        SELECT COALESCE(SUM(delta_kwh), 0.0) AS kwh
        FROM telemetry_15m
        WHERE site_id = $1
          AND bucket = $2
          AND direction = 'production'
        """,
        producer_site_id,
        bucket,
    )
    return float(row["kwh"]) if row else 0.0


async def fetch_consumptions_kwh(
    conn: asyncpg.Connection,
    site_ids: list[UUID],
    membership_ids: list[UUID],
    bucket: datetime,
) -> dict[UUID, float]:
    """Consumption kWh per participant site for this 15-min bucket."""
    rows = await conn.fetch(
        """
        SELECT t.site_id, COALESCE(SUM(t.delta_kwh), 0.0) AS kwh
        FROM telemetry_15m t
        WHERE t.site_id = ANY($1::uuid[])
          AND t.bucket = $2
          AND t.direction = 'consumption'
        GROUP BY t.site_id
        """,
        [str(s) for s in site_ids],
        bucket,
    )
    # Map site_id → kwh, then remap to membership_id
    site_kwh = {UUID(r["site_id"]): float(r["kwh"]) for r in rows}
    # We need site_id→membership_id mapping built from callers
    return site_kwh


# ─── Main billing run ─────────────────────────────────────────────────────────

async def run_billing_period(
    community_id: UUID,
    period_start: date,
    period_end: date,
    dry_run: bool = False,
) -> dict:
    """
    Compute full billing period for a VZEV community.

    Returns a summary dict with totals. If dry_run=True, no data is written.
    """
    conn: asyncpg.Connection = await asyncpg.connect(settings.database_url)
    try:
        community = await fetch_community(conn, community_id)
        producer_site_id: UUID = community["producer_site_id"]
        feed_in_tariff: float = community["feed_in_tariff_chf_kwh"]
        draw_tariff: float = community["draw_tariff_chf_kwh"]

        members = await fetch_active_members(conn, community_id, period_start, period_end)
        if not members:
            logger.warning("No active members for community %s in period %s", community_id, period_start)
            return {"status": "no_members"}

        # Build lookup: membership_id → site_id and site_id → membership_id
        mbr_to_site: dict[UUID, UUID] = {m.membership_id: m.site_id for m in members}
        site_to_mbr: dict[UUID, UUID] = {m.site_id: m.membership_id for m in members}
        participant_sites = list(mbr_to_site.values())

        # Iterate 15-min intervals
        cursor = datetime.combine(period_start, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_ts = datetime.combine(period_end + timedelta(days=1), datetime.min.time()).replace(tzinfo=timezone.utc)

        # Accumulators per membership
        totals: dict[UUID, dict[str, float]] = {
            m.membership_id: {"allocated_kwh": 0.0, "grid_draw_kwh": 0.0}
            for m in members
        }
        community_production_total = 0.0
        community_feed_in_total = 0.0
        community_draw_total = 0.0

        interval_rows: list[tuple] = []

        while cursor < end_ts:
            production = await fetch_production_kwh(conn, producer_site_id, cursor)
            site_consumptions = await fetch_consumptions_kwh(conn, participant_sites, [], cursor)
            # Remap site→membership
            mbr_consumptions = {
                site_to_mbr[sid]: kwh
                for sid, kwh in site_consumptions.items()
                if sid in site_to_mbr
            }

            results = allocate_interval(production, mbr_consumptions, members)

            total_allocated = sum(r.allocated_kwh for r in results)
            feed_in = max(0.0, production - total_allocated)
            community_production_total += production
            community_feed_in_total += feed_in
            community_draw_total += sum(r.grid_draw_kwh for r in results)

            for r in results:
                totals[r.membership_id]["allocated_kwh"] += r.allocated_kwh
                totals[r.membership_id]["grid_draw_kwh"] += r.grid_draw_kwh
                interval_rows.append((
                    cursor,
                    community_id,
                    r.membership_id,
                    r.allocated_kwh,
                    r.grid_draw_kwh,
                    r.effective_share,
                ))

            cursor += timedelta(minutes=15)

        if dry_run:
            logger.info("Dry run complete. Production=%.2f kWh, FeedIn=%.2f kWh",
                        community_production_total, community_feed_in_total)
            return {
                "dry_run": True,
                "community_id": str(community_id),
                "period_start": str(period_start),
                "period_end": str(period_end),
                "total_production_kwh": round(community_production_total, 3),
                "total_feed_in_kwh": round(community_feed_in_total, 3),
                "total_draw_kwh": round(community_draw_total, 3),
                "member_totals": {
                    str(k): {kk: round(vv, 3) for kk, vv in v.items()}
                    for k, v in totals.items()
                },
            }

        async with conn.transaction():
            # Upsert billing period
            bp_id: UUID = await conn.fetchval(
                """
                INSERT INTO vzev_billing_periods
                    (community_id, period_start, period_end,
                     total_production_kwh, total_feed_in_kwh, total_draw_kwh, status)
                VALUES ($1, $2, $3, $4, $5, $6, 'draft')
                ON CONFLICT (community_id, period_start)
                DO UPDATE SET
                    total_production_kwh = EXCLUDED.total_production_kwh,
                    total_feed_in_kwh    = EXCLUDED.total_feed_in_kwh,
                    total_draw_kwh       = EXCLUDED.total_draw_kwh,
                    status               = 'draft',
                    updated_at           = now()
                RETURNING id
                """,
                community_id,
                period_start,
                period_end,
                round(community_production_total, 3),
                round(community_feed_in_total, 3),
                round(community_draw_total, 3),
            )

            # Write interval allocations (bulk insert)
            await conn.executemany(
                """
                INSERT INTO vzev_interval_allocations
                    (time, community_id, membership_id, allocated_kwh, grid_draw_kwh, effective_share)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT DO NOTHING
                """,
                interval_rows,
            )

            # Write invoice lines
            for mbr_id, kwh_totals in totals.items():
                allocated = kwh_totals["allocated_kwh"]
                grid_draw = kwh_totals["grid_draw_kwh"]
                # Community credit: participant pays reduced tariff vs. full grid price
                community_credit = allocated * feed_in_tariff
                grid_draw_cost = grid_draw * draw_tariff
                net = community_credit - grid_draw_cost

                await conn.execute(
                    """
                    INSERT INTO vzev_invoice_lines
                        (billing_period_id, membership_id, community_kwh, grid_draw_kwh,
                         feed_in_kwh, community_credit_chf, grid_draw_cost_chf,
                         feed_in_revenue_chf, net_chf)
                    VALUES ($1, $2, $3, $4, 0.0, $5, $6, 0.0, $7)
                    ON CONFLICT (billing_period_id, membership_id)
                    DO UPDATE SET
                        community_kwh        = EXCLUDED.community_kwh,
                        grid_draw_kwh        = EXCLUDED.grid_draw_kwh,
                        community_credit_chf = EXCLUDED.community_credit_chf,
                        grid_draw_cost_chf   = EXCLUDED.grid_draw_cost_chf,
                        net_chf              = EXCLUDED.net_chf
                    """,
                    bp_id,
                    mbr_id,
                    round(allocated, 3),
                    round(grid_draw, 3),
                    round(community_credit, 2),
                    round(grid_draw_cost, 2),
                    round(net, 2),
                )

            # Mark period finalized
            await conn.execute(
                """
                UPDATE vzev_billing_periods
                SET status = 'finalized', finalized_at = now(), updated_at = now()
                WHERE id = $1
                """,
                bp_id,
            )

        logger.info(
            "Billing finalized for community=%s period=%s→%s  production=%.2f kWh",
            community_id, period_start, period_end, community_production_total,
        )
        return {
            "status": "finalized",
            "billing_period_id": str(bp_id),
            "community_id": str(community_id),
            "period_start": str(period_start),
            "period_end": str(period_end),
            "total_production_kwh": round(community_production_total, 3),
            "total_feed_in_kwh": round(community_feed_in_total, 3),
            "total_draw_kwh": round(community_draw_total, 3),
        }
    finally:
        await conn.close()


if __name__ == "__main__":
    import sys
    from datetime import date

    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 4:
        print("Usage: billing_engine.py <community_id> <YYYY-MM> [--dry-run]")
        sys.exit(1)

    cid = UUID(sys.argv[1])
    year, month = map(int, sys.argv[2].split("-"))
    start = date(year, month, 1)
    # Last day of month
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)

    dry = "--dry-run" in sys.argv

    result = asyncio.run(run_billing_period(cid, start, end, dry_run=dry))
    import json
    print(json.dumps(result, indent=2))
