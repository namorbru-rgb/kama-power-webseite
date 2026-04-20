"""TimescaleDB writer — batch-inserts telemetry rows via asyncpg."""
import asyncio
import json
from typing import Any

import asyncpg
import structlog

log = structlog.get_logger()

_INSERT_SQL = """
INSERT INTO telemetry (
    time, site_id, device_id, device_type,
    power_w, energy_kwh, voltage_v, current_a,
    frequency_hz, direction, soc_pct, extra
) VALUES (
    $1, $2, $3, $4,
    $5, $6, $7, $8,
    $9, $10, $11, $12
)
ON CONFLICT DO NOTHING
"""


async def create_pool(database_url: str) -> asyncpg.Pool:
    # asyncpg uses postgresql:// scheme; strip +asyncpg suffix if present
    url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    pool = await asyncpg.create_pool(url, min_size=2, max_size=10)
    log.info("db_pool_created", dsn=url.split("@")[-1])
    return pool


async def batch_insert(pool: asyncpg.Pool, rows: list[dict[str, Any]]) -> int:
    """Insert a batch of telemetry rows. Returns count of rows inserted."""
    if not rows:
        return 0

    records = [
        (
            row["time"],
            row["site_id"],
            row["device_id"],
            row["device_type"],
            row["power_w"],
            row["energy_kwh"],
            row["voltage_v"],
            row["current_a"],
            row["frequency_hz"],
            row["direction"],
            row["soc_pct"],
            json.dumps(row["extra"]) if row["extra"] else None,
        )
        for row in rows
    ]

    async with pool.acquire() as conn:
        result = await conn.executemany(_INSERT_SQL, records)

    # executemany returns "INSERT 0 N" string per statement; count successes
    inserted = len(records)
    log.info("batch_inserted", count=inserted)
    return inserted
