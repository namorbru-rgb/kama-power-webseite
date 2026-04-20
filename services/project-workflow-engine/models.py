"""Projekt- & Workflow-Engine — Pydantic models."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────
# Kafka event payloads (inbound)
# ─────────────────────────────────────────────────────────────────

class OrderConfirmedEvent(BaseModel):
    """Published by sales-lead-agent on kama.orders.confirmed."""
    event: str = "order.confirmed"
    auftrag_id: str
    customer_name: str
    project_type: str = "solar"
    system_size_kwp: float | None = None
    contract_value_chf: float | None = None
    expected_completion_date: date | None = None
    timestamp: datetime


class ProcurementDeliveredEvent(BaseModel):
    """Published by procurement-agent on kama.procurement.delivered."""
    event: str = "procurement.delivered"
    auftrag_id: str
    suppliers: list[str] = Field(default_factory=list)
    timestamp: datetime


class MontageCompletedEvent(BaseModel):
    """Published by montage-agent on kama.montage.completed."""
    event: str = "montage.completed"
    auftrag_id: str
    auftrag_montage_id: str | None = None
    technician: str | None = None
    timestamp: datetime


# ─────────────────────────────────────────────────────────────────
# Kafka event payloads (outbound)
# ─────────────────────────────────────────────────────────────────

class WorkflowStepReadyEvent(BaseModel):
    event: str = "workflow.step_ready"
    auftrag_id: str
    workflow_id: str
    step_key: str
    step_title: str
    agent_role: str
    paperclip_issue_key: str | None = None
    timestamp: datetime


class WorkflowCompletedEvent(BaseModel):
    event: str = "workflow.completed"
    auftrag_id: str
    workflow_id: str
    timestamp: datetime


# ─────────────────────────────────────────────────────────────────
# DB row models
# ─────────────────────────────────────────────────────────────────

class StepTemplateRow(BaseModel):
    project_type: str
    sequence: int
    step_key: str
    title: str
    description: str | None
    agent_role: str
    estimated_days: int


class WorkflowRow(BaseModel):
    id: UUID
    auftrag_kama_net_id: str
    name: str
    project_type: str
    status: str
    system_size: float | None
    target_completion_date: date | None
    paperclip_goal_id: str | None
    kama_net_project_id: str | None
    created_at: datetime


class WorkflowStepRow(BaseModel):
    id: UUID
    workflow_id: UUID
    step_key: str
    sequence: int
    title: str
    description: str | None
    agent_role: str
    status: str
    paperclip_issue_id: str | None
    paperclip_issue_key: str | None
    paperclip_agent_id: str | None
    target_date: date | None
    started_at: datetime | None
    completed_at: datetime | None


# ─────────────────────────────────────────────────────────────────
# Paperclip API models
# ─────────────────────────────────────────────────────────────────

class PaperclipIssueCreate(BaseModel):
    title: str
    description: str
    status: str = "todo"
    priority: str = "high"
    assigneeAgentId: str | None = None
    projectId: str | None = None
    goalId: str | None = None
    parentId: str | None = None


class PaperclipIssueResponse(BaseModel):
    id: str
    identifier: str
    title: str
    status: str
    assigneeAgentId: str | None = None

    model_config = {"extra": "ignore"}
