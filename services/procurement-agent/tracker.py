"""Delivery Tracker — daily cron job that checks open orders and sends alerts.

Run via: python tracker.py
Intended to be called by a cron entry or docker entrypoint with a schedule.
"""
from __future__ import annotations

import asyncio
from datetime import date

import asyncpg
import structlog

from config import settings
from db import create_pool, get_open_orders
from mailer import send_overdue_alert

log = structlog.get_logger()


async def run_once(pool: asyncpg.Pool) -> None:
    today = date.today()
    orders = await get_open_orders(pool)
    log.info("tracker_run", open_orders=len(orders), today=str(today))

    for order in orders:
        expected: date | None = order["expected_delivery"]
        if expected is None:
            continue

        days_until = (expected - today).days

        if days_until <= 0:
            log.warning(
                "order_overdue",
                order_id=str(order["id"]),
                auftrag_id=order["auftrag_id"],
                supplier=order["supplier"],
                expected=str(expected),
            )
            send_overdue_alert(order["auftrag_id"], order["supplier"], expected)

        elif days_until <= settings.delivery_warn_days:
            log.info(
                "delivery_approaching",
                order_id=str(order["id"]),
                auftrag_id=order["auftrag_id"],
                supplier=order["supplier"],
                days_until=days_until,
            )


async def main() -> None:
    pool = await create_pool(settings.database_url)
    try:
        await run_once(pool)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
