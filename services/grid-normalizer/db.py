"""TimescaleDB writer for canonical GridSignal rows."""
from __future__ import annotations

import json

import psycopg2
import psycopg2.extras
import structlog

from config import settings
from models import GridSignal

log = structlog.get_logger()


class GridSignalWriter:
    """Synchronous psycopg2 writer — keeps the async consumer loop unblocked
    by running DB inserts in a thread pool (called via asyncio.to_thread)."""

    def __init__(self) -> None:
        self._conn: psycopg2.extensions.connection | None = None

    def connect(self) -> None:
        self._conn = psycopg2.connect(settings.database_url)
        self._conn.autocommit = False
        log.info("grid_signal_writer_connected", dsn=settings.database_url)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
        log.info("grid_signal_writer_closed")

    def write_batch(self, signals: list[GridSignal]) -> int:
        """Insert a batch of GridSignals into the grid_signals hypertable.

        Returns the number of rows inserted.
        """
        assert self._conn is not None, "call connect() first"

        rows = [s.to_db_row() for s in signals]
        # Serialise meta dict to JSON string for psycopg2 JSONB
        for row in rows:
            if row["meta"] is not None:
                row["meta"] = json.dumps(row["meta"])

        sql = """
            INSERT INTO grid_signals (
                timestamp, dso_id, signal_type, value, unit,
                location_eic, source, quality, resolution, period_end, meta
            ) VALUES (
                %(timestamp)s, %(dso_id)s, %(signal_type)s, %(value)s, %(unit)s,
                %(location_eic)s, %(source)s, %(quality)s, %(resolution)s,
                %(period_end)s, %(meta)s
            )
            ON CONFLICT DO NOTHING
        """
        with self._conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, sql, rows, page_size=200)
        self._conn.commit()
        log.info("grid_signals_written", count=len(rows))
        return len(rows)
