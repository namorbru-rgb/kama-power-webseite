"""
Projekt- & Workflow-Engine — REST API router
============================================
Provides read/write access to project workflows and their steps.

  GET  /projects                   — list all workflows (with pagination)
  GET  /projects/{workflow_id}     — workflow detail + steps
  GET  /projects/auftrag/{id}      — workflow by Auftrag KAMA-net ID
  POST /projects/{workflow_id}/steps/{step_key}/done
                                   — manually mark a step done (human override)
  POST /projects/{workflow_id}/steps/{step_key}/skip
                                   — skip a step
  POST /projects/{workflow_id}/steps/{step_key}/block
                                   — flag a step as blocked
  GET  /projects/{workflow_id}/events
                                   — audit log for a workflow
"""

from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db

router = APIRouter(prefix="/projects", tags=["projects"])


# ─────────────────────────────────────────────────────────────────
# Response models
# ─────────────────────────────────────────────────────────────────

class WorkflowStepOut(BaseModel):
    id: UUID
    step_key: str
    sequence: int
    title: str
    description: Optional[str]
    agent_role: str
    status: str
    paperclip_issue_key: Optional[str]
    target_date: Optional[date]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    blocker_note: Optional[str]


class WorkflowOut(BaseModel):
    id: UUID
    auftrag_kama_net_id: str
    name: str
    project_type: str
    status: str
    system_size: Optional[float]
    target_completion_date: Optional[date]
    actual_completion_date: Optional[date]
    kama_net_project_id: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    steps: list[WorkflowStepOut] = []
    progress_pct: float = 0.0


class WorkflowListItem(BaseModel):
    id: UUID
    auftrag_kama_net_id: str
    name: str
    project_type: str
    status: str
    system_size: Optional[float]
    target_completion_date: Optional[date]
    created_at: datetime
    total_steps: int
    done_steps: int
    progress_pct: float


class WorkflowListResponse(BaseModel):
    total: int
    offset: int
    limit: int
    workflows: list[WorkflowListItem]
    as_of: datetime


class WorkflowEventOut(BaseModel):
    id: UUID
    event_type: str
    step_key: Optional[str]
    payload: dict
    source: str
    created_at: datetime


class BlockRequest(BaseModel):
    note: str


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _progress(steps: list) -> float:
    if not steps:
        return 0.0
    done = sum(1 for s in steps if s["status"] in ("done", "skipped"))
    return round(done / len(steps) * 100, 1)


# ─────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────

@router.get("", response_model=WorkflowListResponse)
async def list_workflows(
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None, description="Filter by status"),
    project_type: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """List all project workflows with progress summary."""
    where_clauses = ["TRUE"]
    if status:
        where_clauses.append(f"w.status = '{status}'")
    if project_type:
        where_clauses.append(f"w.project_type = '{project_type}'")
    where = " AND ".join(where_clauses)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM project_workflows w WHERE {where}")
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        text(f"""
            SELECT
                w.*,
                COUNT(s.id) AS total_steps,
                COUNT(s.id) FILTER (WHERE s.status IN ('done', 'skipped')) AS done_steps
            FROM project_workflows w
            LEFT JOIN workflow_steps s ON s.workflow_id = w.id
            WHERE {where}
            GROUP BY w.id
            ORDER BY w.created_at DESC
            LIMIT {limit} OFFSET {offset}
        """)
    )
    rows = result.mappings().all()

    workflows = [
        WorkflowListItem(
            id=r["id"],
            auftrag_kama_net_id=r["auftrag_kama_net_id"],
            name=r["name"],
            project_type=r["project_type"],
            status=r["status"],
            system_size=r["system_size"],
            target_completion_date=r["target_completion_date"],
            created_at=r["created_at"],
            total_steps=r["total_steps"] or 0,
            done_steps=r["done_steps"] or 0,
            progress_pct=round(
                (r["done_steps"] or 0) / (r["total_steps"] or 1) * 100, 1
            ),
        )
        for r in rows
    ]

    return WorkflowListResponse(
        total=total,
        offset=offset,
        limit=limit,
        workflows=workflows,
        as_of=datetime.now(timezone.utc),
    )


@router.get("/auftrag/{auftrag_id}", response_model=WorkflowOut)
async def get_workflow_by_auftrag(
    auftrag_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Look up a workflow by KAMA-net Auftrag ID."""
    result = await db.execute(
        text("SELECT * FROM project_workflows WHERE auftrag_kama_net_id = :id"),
        {"id": auftrag_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return await _build_workflow_out(db, dict(row))


@router.get("/{workflow_id}", response_model=WorkflowOut)
async def get_workflow(
    workflow_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get full workflow detail including all steps."""
    result = await db.execute(
        text("SELECT * FROM project_workflows WHERE id = :id"),
        {"id": str(workflow_id)},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return await _build_workflow_out(db, dict(row))


async def _build_workflow_out(db: AsyncSession, wf: dict) -> WorkflowOut:
    steps_result = await db.execute(
        text("SELECT * FROM workflow_steps WHERE workflow_id = :wid ORDER BY sequence"),
        {"wid": str(wf["id"])},
    )
    steps = steps_result.mappings().all()

    return WorkflowOut(
        id=wf["id"],
        auftrag_kama_net_id=wf["auftrag_kama_net_id"],
        name=wf["name"],
        project_type=wf["project_type"],
        status=wf["status"],
        system_size=wf["system_size"],
        target_completion_date=wf["target_completion_date"],
        actual_completion_date=wf["actual_completion_date"],
        kama_net_project_id=wf["kama_net_project_id"],
        started_at=wf["started_at"],
        completed_at=wf["completed_at"],
        created_at=wf["created_at"],
        updated_at=wf["updated_at"],
        steps=[
            WorkflowStepOut(
                id=s["id"],
                step_key=s["step_key"],
                sequence=s["sequence"],
                title=s["title"],
                description=s["description"],
                agent_role=s["agent_role"],
                status=s["status"],
                paperclip_issue_key=s["paperclip_issue_key"],
                target_date=s["target_date"],
                started_at=s["started_at"],
                completed_at=s["completed_at"],
                blocker_note=s["blocker_note"],
            )
            for s in steps
        ],
        progress_pct=_progress(steps),
    )


@router.post("/{workflow_id}/steps/{step_key}/done", response_model=dict)
async def mark_step_done(
    workflow_id: UUID,
    step_key: str,
    db: AsyncSession = Depends(get_db),
):
    """Manually mark a workflow step as done (human override)."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        text(
            "UPDATE workflow_steps SET status = 'done', completed_at = :now, updated_at = :now "
            "WHERE workflow_id = :wid AND step_key = :key RETURNING id"
        ),
        {"now": now, "wid": str(workflow_id), "key": step_key},
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Step not found")
    await db.execute(
        text(
            "INSERT INTO workflow_events (workflow_id, step_id, event_type, payload, source) "
            "VALUES (:wid, :sid, 'step_done', :payload::jsonb, 'api')"
        ),
        {
            "wid": str(workflow_id),
            "sid": str(row[0]),
            "payload": '{"source": "manual_api"}',
        },
    )
    await db.commit()
    return {"status": "done", "step_key": step_key}


@router.post("/{workflow_id}/steps/{step_key}/skip", response_model=dict)
async def skip_step(
    workflow_id: UUID,
    step_key: str,
    db: AsyncSession = Depends(get_db),
):
    """Skip a workflow step (e.g. Netzbetreiber already registered)."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        text(
            "UPDATE workflow_steps SET status = 'skipped', completed_at = :now, updated_at = :now "
            "WHERE workflow_id = :wid AND step_key = :key RETURNING id"
        ),
        {"now": now, "wid": str(workflow_id), "key": step_key},
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Step not found")
    await db.execute(
        text(
            "INSERT INTO workflow_events (workflow_id, step_id, event_type, payload, source) "
            "VALUES (:wid, :sid, 'step_skipped', :payload::jsonb, 'api')"
        ),
        {
            "wid": str(workflow_id),
            "sid": str(row[0]),
            "payload": '{"source": "manual_api"}',
        },
    )
    await db.commit()
    return {"status": "skipped", "step_key": step_key}


@router.post("/{workflow_id}/steps/{step_key}/block", response_model=dict)
async def block_step(
    workflow_id: UUID,
    step_key: str,
    body: BlockRequest,
    db: AsyncSession = Depends(get_db),
):
    """Flag a workflow step as blocked with an explanatory note."""
    result = await db.execute(
        text(
            "UPDATE workflow_steps SET status = 'blocked', blocker_note = :note, updated_at = now() "
            "WHERE workflow_id = :wid AND step_key = :key RETURNING id"
        ),
        {"note": body.note, "wid": str(workflow_id), "key": step_key},
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Step not found")
    import json as _json
    await db.execute(
        text(
            "INSERT INTO workflow_events (workflow_id, step_id, event_type, payload, source) "
            "VALUES (:wid, :sid, 'step_blocked', :payload::jsonb, 'api')"
        ),
        {
            "wid": str(workflow_id),
            "sid": str(row[0]),
            "payload": _json.dumps({"note": body.note}),
        },
    )
    await db.commit()
    return {"status": "blocked", "step_key": step_key, "note": body.note}


@router.get("/{workflow_id}/events", response_model=list[WorkflowEventOut])
async def get_workflow_events(
    workflow_id: UUID,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
):
    """Audit trail: all events for a workflow, newest first."""
    result = await db.execute(
        text("""
            SELECT e.id, e.event_type, e.payload, e.source, e.created_at,
                   s.step_key
            FROM workflow_events e
            LEFT JOIN workflow_steps s ON s.id = e.step_id
            WHERE e.workflow_id = :wid
            ORDER BY e.created_at DESC
            LIMIT :lim
        """),
        {"wid": str(workflow_id), "lim": limit},
    )
    rows = result.mappings().all()
    return [
        WorkflowEventOut(
            id=r["id"],
            event_type=r["event_type"],
            step_key=r["step_key"],
            payload=r["payload"] if isinstance(r["payload"], dict) else {},
            source=r["source"],
            created_at=r["created_at"],
        )
        for r in rows
    ]
