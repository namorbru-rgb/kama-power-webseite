"""Sales & Lead Agent — async database layer (TimescaleDB / asyncpg)."""
from __future__ import annotations

import asyncpg
import structlog

from models import SalesFollowupRow, SalesQuoteRow

log = structlog.get_logger()


async def create_pool(database_url: str) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
    log.info("db_pool_created", dsn=database_url.split("@")[-1])
    return pool


# ── Quotes ─────────────────────────────────────────────────────────────────────


async def insert_quote(pool: asyncpg.Pool, row: SalesQuoteRow) -> None:
    await pool.execute(
        """
        INSERT INTO sales_quotes (
            id, anfrage_kama_net_id, customer_name, customer_email,
            project_type, system_size_kwp, annual_yield_kwh, quote_value_chf,
            status, sent_at, expires_at, body_markdown, email_message_id,
            kama_net_quote_id, notes
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
        ON CONFLICT DO NOTHING
        """,
        row.id,
        row.anfrage_kama_net_id,
        row.customer_name,
        row.customer_email,
        row.project_type,
        row.system_size_kwp,
        row.annual_yield_kwh,
        row.quote_value_chf,
        row.status,
        row.sent_at,
        row.expires_at,
        row.body_markdown,
        row.email_message_id,
        row.kama_net_quote_id,
        row.notes,
    )


async def get_quote_by_anfrage(
    pool: asyncpg.Pool, anfrage_kama_net_id: str
) -> asyncpg.Record | None:
    return await pool.fetchrow(
        "SELECT * FROM sales_quotes WHERE anfrage_kama_net_id = $1 ORDER BY created_at DESC LIMIT 1",
        anfrage_kama_net_id,
    )


async def get_quote_by_email_message_id(
    pool: asyncpg.Pool, email_message_id: str
) -> asyncpg.Record | None:
    return await pool.fetchrow(
        "SELECT * FROM sales_quotes WHERE email_message_id = $1",
        email_message_id,
    )


async def update_quote_status(
    pool: asyncpg.Pool,
    quote_id: str,
    status: str,
    *,
    sent_at: object | None = None,
    accepted_at: object | None = None,
    rejected_at: object | None = None,
    email_message_id: str | None = None,
) -> None:
    await pool.execute(
        """
        UPDATE sales_quotes
        SET status             = $2,
            sent_at            = COALESCE($3, sent_at),
            accepted_at        = COALESCE($4, accepted_at),
            rejected_at        = COALESCE($5, rejected_at),
            email_message_id   = COALESCE($6, email_message_id),
            updated_at         = now()
        WHERE id = $1::uuid
        """,
        quote_id,
        status,
        sent_at,
        accepted_at,
        rejected_at,
        email_message_id,
    )


async def expire_overdue_quotes(pool: asyncpg.Pool) -> int:
    result = await pool.execute(
        """
        UPDATE sales_quotes
        SET status = 'expired', updated_at = now()
        WHERE status = 'sent'
          AND expires_at < now()
        """
    )
    count = int(result.split()[-1])
    if count:
        log.info("quotes_expired", count=count)
    return count


# ── Follow-ups ─────────────────────────────────────────────────────────────────


async def insert_followup(pool: asyncpg.Pool, row: SalesFollowupRow) -> None:
    await pool.execute(
        """
        INSERT INTO sales_followups (
            id, quote_id, anfrage_kama_net_id, scheduled_at,
            status, attempt_number
        ) VALUES ($1,$2,$3,$4,$5,$6)
        ON CONFLICT DO NOTHING
        """,
        row.id,
        row.quote_id,
        row.anfrage_kama_net_id,
        row.scheduled_at,
        row.status,
        row.attempt_number,
    )


async def get_due_followups(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    """Return all pending follow-ups whose scheduled_at has passed."""
    return await pool.fetch(
        """
        SELECT f.*, q.customer_name, q.customer_email,
               q.project_type, q.system_size_kwp, q.quote_value_chf,
               q.body_markdown, q.status AS quote_status
        FROM sales_followups f
        JOIN sales_quotes q ON q.id = f.quote_id
        WHERE f.status = 'pending'
          AND f.scheduled_at <= now()
          AND q.status = 'sent'
        ORDER BY f.scheduled_at ASC
        """
    )


async def cancel_followups_for_quote(
    pool: asyncpg.Pool, quote_id: str
) -> None:
    await pool.execute(
        """
        UPDATE sales_followups
        SET status = 'cancelled', updated_at = now()
        WHERE quote_id = $1::uuid
          AND status = 'pending'
        """,
        quote_id,
    )


async def mark_followup_sent(
    pool: asyncpg.Pool,
    followup_id: str,
    email_message_id: str | None = None,
) -> None:
    await pool.execute(
        """
        UPDATE sales_followups
        SET status = 'sent',
            sent_at = now(),
            email_message_id = COALESCE($2, email_message_id),
            updated_at = now()
        WHERE id = $1::uuid
        """,
        followup_id,
        email_message_id,
    )
