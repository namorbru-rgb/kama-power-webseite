"""Montage Agent — domain models."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Kafka event models ────────────────────────────────────────────────────────


class OrderConfirmedEvent(BaseModel):
    """Consumed from kama.orders.confirmed."""

    event: str = "order.confirmed"
    auftrag_id: str
    project_type: Literal["solar", "bess", "vzev", "combined"] = "solar"
    system_size_kwp: float | None = None
    customer_name: str = ""


class ProcurementDeliveredEvent(BaseModel):
    """Consumed from kama.procurement.delivered — materials arrived."""

    event: str
    auftrag_id: str
    order_id: str
    supplier: str
    timestamp: str


class MontageProgressEvent(BaseModel):
    """Consumed from kama.montage.progress — field progress update."""

    event: str = "montage.progress"
    montage_id: str
    auftrag_id: str
    technician_id: str
    # list of position IDs that are now completed
    completed_position_ids: list[str] = Field(default_factory=list)
    notes: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# ── KAMA-net resource models ──────────────────────────────────────────────────


class Technician(BaseModel):
    """Entry from KAMA-net app_technicians."""

    id: str
    name: str
    telegram_chat_id: str | None = None
    phone: str | None = None
    skills: list[str] = Field(default_factory=list)  # ["solar", "bess", "vzev"]
    # ISO date strings of blocked days (vacation, training, etc.)
    blocked_dates: list[str] = Field(default_factory=list)


class MaterialItem(BaseModel):
    """Single material line from procurement_bom / KAMA-net."""

    article_id: str
    article_name: str
    qty_required: float
    unit: str = "Stk"
    available: bool = False


# ── DB row models ─────────────────────────────────────────────────────────────


class MontageAuftragRow(BaseModel):
    """Row in montage_auftraege."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    auftrag_id: str
    customer_name: str = ""
    project_type: str = "solar"
    system_size_kwp: float | None = None
    # planned → materials_ready → assigned → in_progress → done | cancelled
    status: str = "planned"
    assigned_technician_id: str | None = None
    planned_start_date: date | None = None
    actual_start_date: date | None = None
    actual_end_date: date | None = None
    materials_ready: bool = False
    notes: str | None = None


class MontagePositionRow(BaseModel):
    """One installation step / component per montage order."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    montage_id: uuid.UUID
    article_id: str | None = None
    description: str
    qty_required: float = 1.0
    unit: str = "Stk"
    sequence: int = 0
    # open → in_progress → done | skipped
    status: str = "open"
    completed_at: datetime | None = None
    notes: str | None = None


class MontageProtokollRow(BaseModel):
    """Acceptance protocol (Abnahmeprotokoll) generated at completion."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    montage_id: uuid.UUID
    auftrag_id: str
    customer_name: str = ""
    technician_id: str | None = None
    technician_name: str | None = None
    completed_positions: int = 0
    total_positions: int = 0
    body_markdown: str = ""
    # Once handed over to Meldewesen
    handed_over_at: datetime | None = None
    kama_net_id: str | None = None


# ── Comm request (for Kafka) ──────────────────────────────────────────────────


class CommSendRequest(BaseModel):
    """Published to kama.comm.send_request for the Communication Agent."""

    event: Literal["comm.send_request"] = "comm.send_request"
    channel: Literal["telegram", "email", "whatsapp", "internal"]
    recipient: str
    subject: str | None = None
    body: str
    context: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
