"""Montage Agent — async database layer (TimescaleDB / asyncpg)."""
from __future__ import annotations

import asyncpg
import structlog

from models import MontageAuftragRow, MontagePositionRow, MontageProtokollRow

log = structlog.get_logger()


async def create_pool(database_url: str) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
    log.info("db_pool_created", dsn=database_url.split("@")[-1])
    return pool


# ── Montage order ──────────────────────────────────────────────────────────────


async def insert_montage_auftrag(
    pool: asyncpg.Pool, row: MontageAuftragRow
) -> None:
    await pool.execute(
        """
        INSERT INTO montage_auftraege (
            id, auftrag_id, customer_name, project_type, system_size_kwp,
            status, assigned_technician_id, planned_start_date,
            actual_start_date, actual_end_date, materials_ready, notes
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
        ON CONFLICT (auftrag_id) DO NOTHING
        """,
        row.id,
        row.auftrag_id,
        row.customer_name,
        row.project_type,
        row.system_size_kwp,
        row.status,
        row.assigned_technician_id,
        row.planned_start_date,
        row.actual_start_date,
        row.actual_end_date,
        row.materials_ready,
        row.notes,
    )


async def update_montage_status(
    pool: asyncpg.Pool,
    montage_id: str,
    status: str,
    *,
    assigned_technician_id: str | None = None,
    planned_start_date: object | None = None,
    materials_ready: bool | None = None,
) -> None:
    await pool.execute(
        """
        UPDATE montage_auftraege
        SET status = $2,
            assigned_technician_id = COALESCE($3, assigned_technician_id),
            planned_start_date = COALESCE($4, planned_start_date),
            materials_ready = COALESCE($5, materials_ready),
            updated_at = now()
        WHERE id = $1
        """,
        montage_id,
        status,
        assigned_technician_id,
        planned_start_date,
        materials_ready,
    )


async def mark_materials_ready(
    pool: asyncpg.Pool, auftrag_id: str
) -> str | None:
    """Set materials_ready=true and return the montage_id if found."""
    row = await pool.fetchrow(
        """
        UPDATE montage_auftraege
        SET materials_ready = true, updated_at = now()
        WHERE auftrag_id = $1
        RETURNING id::text, status, assigned_technician_id
        """,
        auftrag_id,
    )
    if row:
        log.info("materials_ready", auftrag_id=auftrag_id, status=row["status"])
    return row


async def get_montage_by_auftrag(
    pool: asyncpg.Pool, auftrag_id: str
) -> asyncpg.Record | None:
    return await pool.fetchrow(
        "SELECT * FROM montage_auftraege WHERE auftrag_id = $1",
        auftrag_id,
    )


async def get_montage_by_id(
    pool: asyncpg.Pool, montage_id: str
) -> asyncpg.Record | None:
    return await pool.fetchrow(
        "SELECT * FROM montage_auftraege WHERE id = $1::uuid",
        montage_id,
    )


# ── Positions (work steps) ─────────────────────────────────────────────────────


async def insert_positions(
    pool: asyncpg.Pool, rows: list[MontagePositionRow]
) -> None:
    if not rows:
        return
    await pool.executemany(
        """
        INSERT INTO montage_positionen (
            id, montage_id, article_id, description,
            qty_required, unit, sequence, status
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
        ON CONFLICT DO NOTHING
        """,
        [
            (
                r.id,
                r.montage_id,
                r.article_id,
                r.description,
                r.qty_required,
                r.unit,
                r.sequence,
                r.status,
            )
            for r in rows
        ],
    )


async def get_positions(
    pool: asyncpg.Pool, montage_id: str
) -> list[asyncpg.Record]:
    return await pool.fetch(
        "SELECT * FROM montage_positionen WHERE montage_id = $1::uuid ORDER BY sequence",
        montage_id,
    )


async def complete_positions(
    pool: asyncpg.Pool, position_ids: list[str]
) -> None:
    if not position_ids:
        return
    await pool.execute(
        """
        UPDATE montage_positionen
        SET status = 'done', completed_at = now()
        WHERE id = ANY($1::uuid[])
        """,
        position_ids,
    )


# ── Acceptance protocol ────────────────────────────────────────────────────────


async def insert_protokoll(
    pool: asyncpg.Pool, row: MontageProtokollRow
) -> None:
    await pool.execute(
        """
        INSERT INTO montage_protokolle (
            id, montage_id, auftrag_id, customer_name,
            technician_id, technician_name,
            completed_positions, total_positions,
            body_markdown, handed_over_at, kama_net_id
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
        """,
        row.id,
        row.montage_id,
        row.auftrag_id,
        row.customer_name,
        row.technician_id,
        row.technician_name,
        row.completed_positions,
        row.total_positions,
        row.body_markdown,
        row.handed_over_at,
        row.kama_net_id,
    )
