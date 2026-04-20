"""
Projekt- & Workflow-Engine — core orchestration logic.

Responsibilities:
  1. On order confirmed → create project_workflow + workflow_steps + deps
  2. Evaluate which steps are now 'ready' → create Paperclip issues
  3. On downstream events (procurement.delivered, montage.completed) →
     mark the relevant step done → re-evaluate ready steps
  4. Sync project status to KAMA-net fm_projektfortschritt
  5. Emit Kafka events for step_ready and workflow_completed
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import asyncpg
import structlog
from aiokafka import AIOKafkaProducer

import db as dblib
import kama_net_client as kama_net
import paperclip_client as pc
from config import settings
from models import (
    MontageCompletedEvent,
    OrderConfirmedEvent,
    PaperclipIssueCreate,
    ProcurementDeliveredEvent,
    WorkflowCompletedEvent,
    WorkflowStepReadyEvent,
)

log = structlog.get_logger()

# Map step_key to the Kafka event that marks it done.
# Keys: inbound event field / value combination that signals completion.
_STEP_KEY_DONE_BY_EVENT: dict[str, str] = {
    "materialbeschaffung": "procurement.delivered",
    "montage_terminieren": "montage.completed",
    "ibn_abnahme": "montage.completed",       # IBN = final montage completion
    "montage_inbetriebnahme": "montage.completed",
}


class WorkflowEngine:
    def __init__(self, pool: asyncpg.Pool, producer: AIOKafkaProducer) -> None:
        self._pool = pool
        self._producer = producer

    # ─────────────────────────────────────────────────────────────
    # Public event handlers
    # ─────────────────────────────────────────────────────────────

    async def on_order_confirmed(self, event: OrderConfirmedEvent) -> None:
        """Create a new project workflow when an order is confirmed."""
        log.info("order_confirmed_received", auftrag_id=event.auftrag_id)

        # Idempotency check
        existing = await dblib.get_workflow_by_auftrag(self._pool, event.auftrag_id)
        if existing:
            log.info("workflow_already_exists", workflow_id=str(existing["id"]))
            return

        name = f"{event.project_type.upper()} — {event.customer_name}"
        workflow = await dblib.create_workflow(
            self._pool,
            auftrag_kama_net_id=event.auftrag_id,
            name=name,
            project_type=event.project_type,
            system_size=event.system_size_kwp,
            target_completion_date=event.expected_completion_date,
        )
        workflow_id = workflow["id"]
        log.info("workflow_created", workflow_id=str(workflow_id), name=name)

        # Load step templates
        templates = await dblib.fetch_step_templates(self._pool, event.project_type)
        if not templates:
            log.error(
                "no_step_templates_for_type",
                project_type=event.project_type,
                workflow_id=str(workflow_id),
            )
            return

        # Compute target dates (cumulative from today)
        start_date = date.today()
        cumulative_days = 0
        step_rows: list[dict[str, Any]] = []
        dep_pairs: list[tuple[str, str]] = []

        for tmpl in templates:
            cumulative_days += tmpl["estimated_days"]
            target = start_date + timedelta(days=cumulative_days)

            # Initial status: first step (no deps) is immediately 'ready'
            requires = tmpl["requires_keys"] or []
            initial_status = "ready" if not requires else "pending"

            step_rows.append({
                "step_key": tmpl["step_key"],
                "sequence": tmpl["sequence"],
                "title": tmpl["title"],
                "description": tmpl["description"],
                "agent_role": tmpl["agent_role"],
                "status": initial_status,
                "target_date": target,
            })
            for req_key in requires:
                dep_pairs.append((tmpl["step_key"], req_key))

        # Persist steps and deps
        step_records = await dblib.insert_workflow_steps(self._pool, workflow_id, step_rows)
        await dblib.insert_workflow_step_deps(self._pool, workflow_id, dep_pairs)

        # Audit log
        await dblib.log_event(
            self._pool,
            workflow_id=workflow_id,
            event_type="workflow_created",
            payload={"auftrag_id": event.auftrag_id, "project_type": event.project_type},
            source="kafka",
        )

        # Sync to KAMA-net
        kama_net_project_id = await kama_net.create_project(
            event.auftrag_id, name, event.project_type, event.system_size_kwp
        )
        if kama_net_project_id:
            await dblib.set_workflow_kama_net_project(
                self._pool, workflow_id, kama_net_project_id
            )
        await dblib.update_workflow_status(self._pool, workflow_id, "active")

        # Create Paperclip issues for all 'ready' steps
        ready_steps = [s for s in step_records if dict(s)["status"] == "ready"]
        for step in ready_steps:
            await self._create_paperclip_issue_for_step(
                workflow_id=workflow_id,
                step_id=step["id"],
                step_key=step["step_key"],
                step_title=step["title"],
                step_description=step["description"],
                agent_role=step["agent_role"],
                project_name=name,
                auftrag_id=event.auftrag_id,
            )

    async def on_procurement_delivered(self, event: ProcurementDeliveredEvent) -> None:
        """Mark 'materialbeschaffung' step done when material is delivered."""
        log.info("procurement_delivered_received", auftrag_id=event.auftrag_id)
        await self._mark_step_done_by_event_type(
            auftrag_id=event.auftrag_id,
            step_key="materialbeschaffung",
            event_payload={
                "suppliers": event.suppliers,
                "timestamp": event.timestamp.isoformat(),
            },
        )

    async def on_montage_completed(self, event: MontageCompletedEvent) -> None:
        """Mark montage-related steps done when assembly is completed."""
        log.info("montage_completed_received", auftrag_id=event.auftrag_id)
        # IBN + Abnahme is the terminal montage step; mark both if present
        for step_key in ("montage_terminieren", "ibn_abnahme", "montage_inbetriebnahme"):
            await self._mark_step_done_by_event_type(
                auftrag_id=event.auftrag_id,
                step_key=step_key,
                event_payload={
                    "technician": event.technician,
                    "timestamp": event.timestamp.isoformat(),
                },
                required=False,
            )

    # ─────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────

    async def _mark_step_done_by_event_type(
        self,
        auftrag_id: str,
        step_key: str,
        event_payload: dict[str, Any],
        required: bool = True,
    ) -> None:
        workflow = await dblib.get_workflow_by_auftrag(self._pool, auftrag_id)
        if not workflow:
            log.warning("workflow_not_found_for_auftrag", auftrag_id=auftrag_id)
            return

        workflow_id = workflow["id"]
        step = await dblib.get_step(self._pool, workflow_id, step_key)
        if not step:
            if required:
                log.warning(
                    "step_not_found", workflow_id=str(workflow_id), step_key=step_key
                )
            return

        if step["status"] in ("done", "skipped"):
            log.info(
                "step_already_done",
                workflow_id=str(workflow_id),
                step_key=step_key,
                status=step["status"],
            )
            return

        await dblib.update_step_status(
            self._pool,
            step_id=step["id"],
            status="done",
            completed_at=datetime.now(timezone.utc),
        )
        await dblib.log_event(
            self._pool,
            workflow_id=workflow_id,
            step_id=step["id"],
            event_type="step_done",
            payload={"step_key": step_key, **event_payload},
            source="kafka",
        )
        log.info("step_marked_done", workflow_id=str(workflow_id), step_key=step_key)

        # Re-evaluate: unlock newly ready steps
        await self._advance_workflow(workflow_id, workflow["auftrag_kama_net_id"], workflow["name"])

    async def _advance_workflow(
        self, workflow_id: UUID, auftrag_id: str, project_name: str
    ) -> None:
        """
        After any step transitions to done/skipped:
        1. Find steps whose prerequisites are all done → transition to 'ready'
        2. Create Paperclip issues for those steps
        3. Check if entire workflow is complete
        """
        newly_ready = await dblib.get_unblocked_ready_steps(self._pool, workflow_id)

        for step in newly_ready:
            step_id = step["id"]
            step_key = step["step_key"]
            await dblib.update_step_status(self._pool, step_id=step_id, status="ready")
            await dblib.log_event(
                self._pool,
                workflow_id=workflow_id,
                step_id=step_id,
                event_type="step_ready",
                payload={"step_key": step_key},
                source="engine",
            )
            await self._create_paperclip_issue_for_step(
                workflow_id=workflow_id,
                step_id=step_id,
                step_key=step_key,
                step_title=step["title"],
                step_description=step["description"],
                agent_role=step["agent_role"],
                project_name=project_name,
                auftrag_id=auftrag_id,
            )

        # Check completion
        all_steps = await dblib.get_workflow_steps(self._pool, workflow_id)
        all_done = all(s["status"] in ("done", "skipped") for s in all_steps)

        if all_done and all_steps:
            now = datetime.now(timezone.utc)
            await dblib.update_workflow_status(
                self._pool, workflow_id, "completed", completed_at=now
            )
            await dblib.log_event(
                self._pool,
                workflow_id=workflow_id,
                event_type="workflow_completed",
                payload={"auftrag_id": auftrag_id, "completed_at": now.isoformat()},
                source="engine",
            )
            await kama_net.update_project_status(
                await self._get_kama_net_project_id(workflow_id), "completed"
            )
            await self._emit_workflow_completed(auftrag_id, str(workflow_id))
            log.info("workflow_completed", workflow_id=str(workflow_id))

    async def _create_paperclip_issue_for_step(
        self,
        workflow_id: UUID,
        step_id: UUID,
        step_key: str,
        step_title: str,
        step_description: str | None,
        agent_role: str,
        project_name: str,
        auftrag_id: str,
    ) -> None:
        """Create a Paperclip issue for a ready step and link it in the DB."""
        agent_id = pc.get_agent_id_for_role(agent_role)

        description = _build_issue_description(
            step_title=step_title,
            step_description=step_description,
            project_name=project_name,
            auftrag_id=auftrag_id,
            step_key=step_key,
        )

        issue_create = PaperclipIssueCreate(
            title=f"[{project_name}] {step_title}",
            description=description,
            status="todo",
            priority="high",
            assigneeAgentId=agent_id,
            projectId=settings.paperclip_project_id or None,
            goalId=settings.paperclip_goal_id or None,
        )

        try:
            issue = await pc.create_paperclip_issue(issue_create)
            await dblib.set_step_paperclip_issue(
                self._pool, step_id, issue.id, issue.identifier, agent_id
            )
            await dblib.log_event(
                self._pool,
                workflow_id=workflow_id,
                step_id=step_id,
                event_type="paperclip_issue_created",
                payload={
                    "issue_id": issue.id,
                    "issue_key": issue.identifier,
                    "agent_role": agent_role,
                    "agent_id": agent_id,
                },
                source="engine",
            )
            # Emit step_ready event for downstream consumers
            await self._emit_step_ready(
                auftrag_id=auftrag_id,
                workflow_id=str(workflow_id),
                step_key=step_key,
                step_title=step_title,
                agent_role=agent_role,
                issue_key=issue.identifier,
            )
        except Exception as exc:
            log.error(
                "paperclip_issue_create_failed",
                step_key=step_key,
                error=str(exc),
            )

    async def _get_kama_net_project_id(self, workflow_id: UUID) -> str:
        row = await self._pool.fetchrow(
            "SELECT kama_net_project_id FROM project_workflows WHERE id = $1",
            workflow_id,
        )
        return (row and row["kama_net_project_id"]) or ""

    # ─────────────────────────────────────────────────────────────
    # Kafka outbound events
    # ─────────────────────────────────────────────────────────────

    async def _emit_step_ready(
        self,
        auftrag_id: str,
        workflow_id: str,
        step_key: str,
        step_title: str,
        agent_role: str,
        issue_key: str | None,
    ) -> None:
        event = WorkflowStepReadyEvent(
            auftrag_id=auftrag_id,
            workflow_id=workflow_id,
            step_key=step_key,
            step_title=step_title,
            agent_role=agent_role,
            paperclip_issue_key=issue_key,
            timestamp=datetime.now(timezone.utc),
        )
        await self._producer.send_and_wait(
            settings.kafka_topic_workflow_step_ready,
            json.dumps(event.model_dump(mode="json")).encode(),
        )
        log.info("step_ready_event_emitted", step_key=step_key, issue_key=issue_key)

    async def _emit_workflow_completed(self, auftrag_id: str, workflow_id: str) -> None:
        event = WorkflowCompletedEvent(
            auftrag_id=auftrag_id,
            workflow_id=workflow_id,
            timestamp=datetime.now(timezone.utc),
        )
        await self._producer.send_and_wait(
            settings.kafka_topic_workflow_completed,
            json.dumps(event.model_dump(mode="json")).encode(),
        )
        log.info("workflow_completed_event_emitted", auftrag_id=auftrag_id)


# ─────────────────────────────────────────────────────────────────
# Issue description builder
# ─────────────────────────────────────────────────────────────────

def _build_issue_description(
    step_title: str,
    step_description: str | None,
    project_name: str,
    auftrag_id: str,
    step_key: str,
) -> str:
    lines = [
        f"## {step_title}",
        "",
        f"**Projekt:** {project_name}  ",
        f"**Auftrag-ID:** `{auftrag_id}`  ",
        f"**Step:** `{step_key}`",
        "",
    ]
    if step_description:
        lines += [
            "### Aufgabe",
            step_description,
            "",
        ]
    lines += [
        "### Abschluss",
        "Wenn dieser Schritt erledigt ist, dieses Issue auf `done` setzen.",
        "Die Projekt-Engine schaltet automatisch den nächsten Schritt frei.",
    ]
    return "\n".join(lines)
