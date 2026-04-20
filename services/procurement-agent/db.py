"""Procurement Agent — TimescaleDB repository."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

import asyncpg
import structlog

from models import ProcurementOrderRow, ProcurementOrderItemRow

log = structlog.get_logger()


async def create_pool(database_url: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(database_url, min_size=1, max_size=5)


async def upsert_bom(pool: asyncpg.Pool, auftrag_id: str, items: list[dict[str, Any]]) -> None:
    """Insert/replace BOM for an order (idempotent)."""
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO procurement_bom (auftrag_id, article_id, article_name, qty_required, unit)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (auftrag_id, article_id)
            DO UPDATE SET qty_required = EXCLUDED.qty_required
            """,
            [
                (auftrag_id, i["article_id"], i["article_name"], i["qty_required"], i["unit"])
                for i in items
            ],
        )


async def insert_order(
    pool: asyncpg.Pool, order: ProcurementOrderRow, items: list[ProcurementOrderItemRow]
) -> None:
    """Insert a procurement order and its line items atomically."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO procurement_orders
                    (id, auftrag_id, supplier, status, ordered_at, expected_delivery,
                     email_message_id, notes)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                order.id,
                order.auftrag_id,
                order.supplier,
                order.status,
                order.ordered_at,
                order.expected_delivery,
                order.email_message_id,
                order.notes,
            )
            if items:
                await conn.executemany(
                    """
                    INSERT INTO procurement_order_items
                        (id, order_id, article_id, article_name, qty_ordered, unit_price_chf, unit)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    [
                        (
                            i.id,
                            i.order_id,
                            i.article_id,
                            i.article_name,
                            i.qty_ordered,
                            i.unit_price_chf,
                            i.unit,
                        )
                        for i in items
                    ],
                )
    log.info("order_inserted", order_id=str(order.id), supplier=order.supplier)


async def mark_order_sent(
    pool: asyncpg.Pool, order_id: uuid.UUID, message_id: str, expected_delivery: date | None
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE procurement_orders
            SET status = 'sent',
                ordered_at = $2,
                email_message_id = $3,
                expected_delivery = $4,
                updated_at = $5
            WHERE id = $1
            """,
            order_id,
            datetime.now(timezone.utc),
            message_id,
            expected_delivery,
            datetime.now(timezone.utc),
        )


async def get_open_orders(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Return all sent/confirmed orders with expected_delivery set."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, auftrag_id, supplier, status, expected_delivery, ordered_at
            FROM procurement_orders
            WHERE status IN ('sent', 'confirmed')
              AND expected_delivery IS NOT NULL
            ORDER BY expected_delivery ASC
            """
        )
    return [dict(r) for r in rows]


async def mark_order_delivered(pool: asyncpg.Pool, order_id: uuid.UUID) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE procurement_orders
            SET status = 'delivered',
                delivered_at = $2,
                updated_at = $2
            WHERE id = $1
            """,
            order_id,
            datetime.now(timezone.utc),
        )
