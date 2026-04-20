"""Communication Agent — asyncpg pool and DB helpers."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import asyncpg

from models import CommMessageRow, CommSopRow, CommThreadRow


async def create_pool(database_url: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(database_url, min_size=2, max_size=10)


# ─────────────────────────────────────────────────────────────────
# Thread helpers
# ─────────────────────────────────────────────────────────────────


async def upsert_thread(pool: asyncpg.Pool, row: CommThreadRow) -> uuid.UUID:
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """
            INSERT INTO comm_threads
                (id, channel, topic, participant, awaiting_reply_from, context, state)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
            RETURNING id
            """,
            row.id,
            row.channel,
            row.topic,
            row.participant,
            row.awaiting_reply_from,
            json.dumps(row.context),
            row.state,
        )
        return result["id"]


async def resolve_thread(pool: asyncpg.Pool, thread_id: uuid.UUID) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE comm_threads
            SET state = 'resolved', resolved_at = $1, updated_at = $1
            WHERE id = $2
            """,
            datetime.now(timezone.utc),
            thread_id,
        )


# ─────────────────────────────────────────────────────────────────
# Message helpers
# ─────────────────────────────────────────────────────────────────


async def insert_message(pool: asyncpg.Pool, row: CommMessageRow) -> uuid.UUID:
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """
            INSERT INTO comm_messages
                (id, channel, direction, external_id, thread_id,
                 sender, recipient, subject, body, metadata, status,
                 sent_at, received_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11, $12, $13)
            RETURNING id
            """,
            row.id,
            row.channel,
            row.direction,
            row.external_id,
            row.thread_id,
            row.sender,
            row.recipient,
            row.subject,
            row.body,
            json.dumps(row.metadata),
            row.status,
            row.sent_at,
            row.received_at,
        )
        return result["id"]


async def mark_message_replied(pool: asyncpg.Pool, message_id: uuid.UUID) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE comm_messages
            SET status = 'replied', updated_at = $1
            WHERE id = $2
            """,
            datetime.now(timezone.utc),
            message_id,
        )


# ─────────────────────────────────────────────────────────────────
# SOP helpers
# ─────────────────────────────────────────────────────────────────


async def insert_sop(pool: asyncpg.Pool, row: CommSopRow) -> uuid.UUID:
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """
            INSERT INTO comm_sops
                (id, title, domain, body, kama_net_id, source_thread_id, version)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id
            """,
            row.id,
            row.title,
            row.domain,
            row.body,
            row.kama_net_id,
            row.source_thread_id,
            row.version,
        )
        return result["id"]


async def update_sop_kama_net_id(
    pool: asyncpg.Pool, sop_id: uuid.UUID, kama_net_id: str
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE comm_sops SET kama_net_id = $1, updated_at = $2 WHERE id = $3
            """,
            kama_net_id,
            datetime.now(timezone.utc),
            sop_id,
        )
