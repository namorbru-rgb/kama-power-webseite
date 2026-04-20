"""Lager & Logistik Agent — async database layer (asyncpg)."""
from __future__ import annotations

import asyncpg
import structlog

from models import LagerBestandRow, LagerEingangPositionRow, LagerLieferungRow

log = structlog.get_logger()


async def create_pool(database_url: str) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
    log.info("db_pool_created", dsn=database_url.split("@")[-1])
    return pool


# ── Lieferungen (deliveries) ──────────────────────────────────────────────────


async def insert_lieferung(pool: asyncpg.Pool, row: LagerLieferungRow) -> None:
    await pool.execute(
        """
        INSERT INTO lager_lieferungen (
            id, auftrag_id, order_id, supplier, status,
            expected_delivery, eingang_at, bestaetigt_at, bestaetigt_by,
            vorankuendigung_sent_at, eingang_notification_sent_at, notes
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
        ON CONFLICT (order_id) WHERE status NOT IN ('bestaetigt') DO NOTHING
        """,
        row.id,
        row.auftrag_id,
        row.order_id,
        row.supplier,
        row.status,
        row.expected_delivery,
        row.eingang_at,
        row.bestaetigt_at,
        row.bestaetigt_by,
        row.vorankuendigung_sent_at,
        row.eingang_notification_sent_at,
        row.notes,
    )


async def get_lieferung_by_order(
    pool: asyncpg.Pool, order_id: str
) -> asyncpg.Record | None:
    return await pool.fetchrow(
        "SELECT * FROM lager_lieferungen WHERE order_id = $1 AND status != 'bestaetigt' LIMIT 1",
        order_id,
    )


async def get_pending_lieferungen_for_auftrag(
    pool: asyncpg.Pool, auftrag_id: str
) -> list[asyncpg.Record]:
    """Get deliveries in 'eingetroffen' state waiting for employee confirmation."""
    return await pool.fetch(
        """
        SELECT * FROM lager_lieferungen
        WHERE auftrag_id = $1 AND status = 'eingetroffen'
        ORDER BY created_at DESC
        """,
        auftrag_id,
    )


async def get_oldest_pending_eingetroffen(
    pool: asyncpg.Pool,
) -> asyncpg.Record | None:
    """Get the oldest delivery waiting for confirmation (FIFO)."""
    return await pool.fetchrow(
        """
        SELECT * FROM lager_lieferungen
        WHERE status = 'eingetroffen'
        ORDER BY eingang_at ASC NULLS LAST
        LIMIT 1
        """
    )


async def update_lieferung_status(
    pool: asyncpg.Pool,
    lieferung_id: str,
    status: str,
    *,
    eingang_at: object | None = None,
    bestaetigt_at: object | None = None,
    bestaetigt_by: str | None = None,
    vorankuendigung_sent_at: object | None = None,
    eingang_notification_sent_at: object | None = None,
) -> None:
    await pool.execute(
        """
        UPDATE lager_lieferungen
        SET status = $2,
            eingang_at = COALESCE($3, eingang_at),
            bestaetigt_at = COALESCE($4, bestaetigt_at),
            bestaetigt_by = COALESCE($5, bestaetigt_by),
            vorankuendigung_sent_at = COALESCE($6, vorankuendigung_sent_at),
            eingang_notification_sent_at = COALESCE($7, eingang_notification_sent_at),
            updated_at = now()
        WHERE id = $1::uuid
        """,
        lieferung_id,
        status,
        eingang_at,
        bestaetigt_at,
        bestaetigt_by,
        vorankuendigung_sent_at,
        eingang_notification_sent_at,
    )


# ── Inventory (Bestand) ───────────────────────────────────────────────────────


async def upsert_bestand(pool: asyncpg.Pool, row: LagerBestandRow) -> None:
    await pool.execute(
        """
        INSERT INTO lager_bestand (id, article_id, article_name, qty, unit, last_eingang_at)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (article_id) DO UPDATE
        SET qty = lager_bestand.qty + EXCLUDED.qty,
            article_name = EXCLUDED.article_name,
            last_eingang_at = EXCLUDED.last_eingang_at,
            updated_at = now()
        """,
        row.id,
        row.article_id,
        row.article_name,
        row.qty,
        row.unit,
        row.last_eingang_at,
    )


async def get_bestand(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    return await pool.fetch(
        "SELECT * FROM lager_bestand ORDER BY article_name"
    )


# ── Eingang positions ─────────────────────────────────────────────────────────


async def insert_eingang_position(
    pool: asyncpg.Pool, row: LagerEingangPositionRow
) -> None:
    await pool.execute(
        """
        INSERT INTO lager_eingang_positionen (
            id, lieferung_id, article_id, article_name, qty_received, unit
        ) VALUES ($1,$2,$3,$4,$5,$6)
        """,
        row.id,
        row.lieferung_id,
        row.article_id,
        row.article_name,
        row.qty_received,
        row.unit,
    )


async def get_eingang_positionen(
    pool: asyncpg.Pool, lieferung_id: str
) -> list[asyncpg.Record]:
    return await pool.fetch(
        "SELECT * FROM lager_eingang_positionen WHERE lieferung_id = $1::uuid",
        lieferung_id,
    )
