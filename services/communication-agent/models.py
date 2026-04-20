"""Communication Agent — Pydantic models."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────
# Kafka event schemas
# ─────────────────────────────────────────────────────────────────


class CommSendRequest(BaseModel):
    """Inbound Kafka event requesting the agent to send a message."""

    event: Literal["comm.send_request"] = "comm.send_request"
    channel: Literal["email", "telegram", "whatsapp", "internal"]
    recipient: str  # email address, chat_id, or agent id
    subject: str | None = None
    body: str
    context: dict[str, Any] = Field(default_factory=dict)
    # Optional: link to an existing thread
    thread_id: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ProcurementOrderedEvent(BaseModel):
    """Downstream: procurement-agent notified an order was placed."""

    event: str
    auftrag_id: str
    suppliers: list[str]
    timestamp: str


class ProcurementDeliveredEvent(BaseModel):
    """Downstream: procurement-agent notified a delivery arrived."""

    event: str
    auftrag_id: str
    order_id: str
    supplier: str
    timestamp: str


# ─────────────────────────────────────────────────────────────────
# DB row models (for insert helpers)
# ─────────────────────────────────────────────────────────────────


class CommMessageRow(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    channel: str
    direction: str
    external_id: str | None = None
    thread_id: uuid.UUID | None = None
    sender: str | None = None
    recipient: str | None = None
    subject: str | None = None
    body: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: str = "sent"
    sent_at: datetime | None = None
    received_at: datetime | None = None


class CommThreadRow(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    channel: str
    topic: str
    participant: str | None = None
    awaiting_reply_from: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    state: str = "open"


class CommSopRow(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    title: str
    domain: str
    body: str
    kama_net_id: str | None = None
    source_thread_id: uuid.UUID | None = None
    version: int = 1


# ─────────────────────────────────────────────────────────────────
# Internal task request (to Paperclip)
# ─────────────────────────────────────────────────────────────────


class InternalTaskRequest(BaseModel):
    """Represents a structured task to be created as a Paperclip issue."""

    trigger: str
    responsible: str  # agent id or name
    goal: str
    expected_result: str
    deadline_iso: str | None = None
    priority: Literal["critical", "high", "medium", "low"] = "medium"
    context: dict[str, Any] = Field(default_factory=dict)
