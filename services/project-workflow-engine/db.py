"""Projekt- & Workflow-Engine — asyncpg database helpers."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import asyncpg


async def create_pool(dsn: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(dsn, min_size=2, max_size=10)


# ─────────────────────────────────────────────────────────────────
# Step templates
# ─────────────────────────────────────────────────────────────────

async def fetch_step_templates(
    pool: asyncpg.Pool, project_type: str
) -> list[asyncpg.Record]:
    """Return all step templates for a project type, ordered by sequence."""
    return await pool.fetch(
        """
        SELECT t.*, array_agg(d.requires_key) FILTER (WHERE d.requires_key IS NOT NULL)
            AS requires_keys
        FROM workflow_step_templates t
        LEFT JOIN workflow_step_template_deps d
            ON d.project_type = t.project_type AND d.step_key = t.step_key
        WHERE t.project_type = $1
        GROUP BY t.id, t.project_type, t.sequence, t.step_key, t.title,
                 t.description, t.agent_role, t.estimated_days, t.created_at
        ORDER BY t.sequence
        """,
        project_type,
    )


# ─────────────────────────────────────────────────────────────────
# Workflow CRUD
# ─────────────────────────────────────────────────────────────────

async def get_workflow_by_auftrag(
    pool: asyncpg.Pool, auftrag_kama_net_id: str
) -> asyncpg.Record | None:
    return await pool.fetchrow(
        "SELECT * FROM project_workflows WHERE auftrag_kama_net_id = $1",
        auftrag_kama_net_id,
    )


async def create_workflow(
    pool: asyncpg.Pool,
    auftrag_kama_net_id: str,
    name: str,
    project_type: str,
    system_size: float | None,
    target_completion_date: Any,
) -> asyncpg.Record:
    return await pool.fetchrow(
        """
        INSERT INTO project_workflows
            (auftrag_kama_net_id, name, project_type, status, system_size,
             target_completion_date)
        VALUES ($1, $2, $3, 'pending', $4, $5)
        RETURNING *
        """,
        auftrag_kama_net_id,
        name,
        project_type,
        system_size,
        target_completion_date,
    )


async def update_workflow_status(
    pool: asyncpg.Pool,
    workflow_id: UUID,
    status: str,
    completed_at: datetime | None = None,
) -> None:
    if status == "active":
        await pool.execute(
            """
            UPDATE project_workflows
            SET status = $2, started_at = COALESCE(started_at, now()), updated_at = now()
            WHERE id = $1
            """,
            workflow_id, status,
        )
    elif status == "completed":
        await pool.execute(
            """
            UPDATE project_workflows
            SET status = $2, completed_at = $3, updated_at = now()
            WHERE id = $1
            """,
            workflow_id, status, completed_at or datetime.now(timezone.utc),
        )
    else:
        await pool.execute(
            "UPDATE project_workflows SET status = $2, updated_at = now() WHERE id = $1",
            workflow_id, status,
        )


async def set_workflow_kama_net_project(
    pool: asyncpg.Pool, workflow_id: UUID, kama_net_project_id: str
) -> None:
    await pool.execute(
        "UPDATE project_workflows SET kama_net_project_id = $2 WHERE id = $1",
        workflow_id, kama_net_project_id,
    )


# ─────────────────────────────────────────────────────────────────
# Workflow steps CRUD
# ─────────────────────────────────────────────────────────────────

async def insert_workflow_steps(
    pool: asyncpg.Pool,
    workflow_id: UUID,
    steps: list[dict[str, Any]],
) -> list[asyncpg.Record]:
    """Bulk insert steps for a workflow. Returns inserted rows."""
    records = []
    async with pool.acquire() as conn:
        async with conn.transaction():
            for s in steps:
                row = await conn.fetchrow(
                    """
                    INSERT INTO workflow_steps
                        (workflow_id, step_key, sequence, title, description,
                         agent_role, status, target_date)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    RETURNING *
                    """,
                    workflow_id,
                    s["step_key"],
                    s["sequence"],
                    s["title"],
                    s.get("description"),
                    s["agent_role"],
                    s.get("status", "pending"),
                    s.get("target_date"),
                )
                records.append(row)
    return records


async def insert_workflow_step_deps(
    pool: asyncpg.Pool, workflow_id: UUID, deps: list[tuple[str, str]]
) -> None:
    """Insert (step_key, requires_key) dependency pairs for a workflow."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            for step_key, requires_key in deps:
                await conn.execute(
                    """
                    INSERT INTO workflow_step_deps (workflow_id, step_key, requires_key)
                    VALUES ($1, $2, $3) ON CONFLICT DO NOTHING
                    """,
                    workflow_id, step_key, requires_key,
                )


async def get_workflow_steps(
    pool: asyncpg.Pool, workflow_id: UUID
) -> list[asyncpg.Record]:
    return await pool.fetch(
        "SELECT * FROM workflow_steps WHERE workflow_id = $1 ORDER BY sequence",
        workflow_id,
    )


async def get_step(
    pool: asyncpg.Pool, workflow_id: UUID, step_key: str
) -> asyncpg.Record | None:
    return await pool.fetchrow(
        "SELECT * FROM workflow_steps WHERE workflow_id = $1 AND step_key = $2",
        workflow_id, step_key,
    )


async def update_step_status(
    pool: asyncpg.Pool,
    step_id: UUID,
    status: str,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    blocker_note: str | None = None,
) -> None:
    await pool.execute(
        """
        UPDATE workflow_steps
        SET status = $2,
            started_at = COALESCE($3, started_at),
            completed_at = COALESCE($4, completed_at),
            blocker_note = COALESCE($5, blocker_note),
            updated_at = now()
        WHERE id = $1
        """,
        step_id, status, started_at, completed_at, blocker_note,
    )


async def set_step_paperclip_issue(
    pool: asyncpg.Pool,
    step_id: UUID,
    issue_id: str,
    issue_key: str,
    agent_id: str | None,
) -> None:
    await pool.execute(
        """
        UPDATE workflow_steps
        SET paperclip_issue_id = $2, paperclip_issue_key = $3,
            paperclip_agent_id = $4, updated_at = now()
        WHERE id = $1
        """,
        step_id, issue_id, issue_key, agent_id,
    )


async def get_unblocked_ready_steps(
    pool: asyncpg.Pool, workflow_id: UUID
) -> list[asyncpg.Record]:
    """
    Return steps that are still 'pending' but whose all required steps are 'done'.
    These are newly unblocked and should transition to 'ready'.
    """
    return await pool.fetch(
        """
        SELECT s.*
        FROM workflow_steps s
        WHERE s.workflow_id = $1
          AND s.status = 'pending'
          AND NOT EXISTS (
            SELECT 1 FROM workflow_step_deps d
            JOIN workflow_steps req
                ON req.workflow_id = d.workflow_id AND req.step_key = d.requires_key
            WHERE d.workflow_id = s.workflow_id
              AND d.step_key = s.step_key
              AND req.status NOT IN ('done', 'skipped')
          )
        ORDER BY s.sequence
        """,
        workflow_id,
    )


# ─────────────────────────────────────────────────────────────────
# Workflow events
# ─────────────────────────────────────────────────────────────────

async def log_event(
    pool: asyncpg.Pool,
    workflow_id: UUID,
    event_type: str,
    payload: dict[str, Any],
    step_id: UUID | None = None,
    source: str = "kafka",
    kafka_offset: int | None = None,
) -> None:
    await pool.execute(
        """
        INSERT INTO workflow_events
            (workflow_id, step_id, event_type, payload, source, kafka_offset)
        VALUES ($1, $2, $3, $4::jsonb, $5, $6)
        """,
        workflow_id,
        step_id,
        event_type,
        json.dumps(payload),
        source,
        kafka_offset,
    )
