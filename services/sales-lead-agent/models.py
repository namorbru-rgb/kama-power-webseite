"""Sales & Lead Agent — Pydantic models for Kafka events and DB rows."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────
# Kafka inbound events
# ─────────────────────────────────────────────────────────────────


class LeadInboundEvent(BaseModel):
    """Fired when a new inquiry arrives in KAMA-net (app_inquiries)."""

    kama_net_id: str
    customer_name: str
    customer_email: str | None = None
    customer_phone: str | None = None
    project_type: str = "solar"
    municipality: str | None = None
    canton: str | None = None
    # Roof area (m²) or consumption (kWh/yr) — optional inputs for solar calc
    roof_area_m2: float | None = None
    annual_consumption_kwh: float | None = None
    notes: str | None = None
    source: str | None = None  # website | facebook | referral | kama-net
    received_at: datetime = Field(default_factory=lambda: datetime.utcnow())


class CommReplyReceivedEvent(BaseModel):
    """Incoming email/message reply — check if it's a lead acceptance."""

    message_id: str
    in_reply_to: str | None = None  # References original email Message-ID
    channel: str  # email | telegram | whatsapp
    sender_email: str | None = None
    body: str
    received_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    context: dict[str, Any] = Field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────
# Kafka outbound events
# ─────────────────────────────────────────────────────────────────


class CommSendRequest(BaseModel):
    """Request to Communication Agent to dispatch a message."""

    channel: str  # email | telegram | whatsapp
    recipient: str  # email address or chat_id
    subject: str | None = None
    body: str
    in_reply_to: str | None = None  # Message-ID for email threading
    context: dict[str, Any] = Field(default_factory=dict)


class OrderConfirmedEvent(BaseModel):
    """Emitted when a lead is converted to a confirmed order."""

    event: str = "order.confirmed"
    auftrag_id: str
    anfrage_kama_net_id: str
    customer_name: str
    customer_email: str | None = None
    project_type: str
    system_size_kwp: float | None = None
    contract_value_chf: float | None = None
    timestamp: str


# ─────────────────────────────────────────────────────────────────
# DB row models
# ─────────────────────────────────────────────────────────────────


class SalesQuoteRow(BaseModel):
    id: uuid.UUID
    anfrage_kama_net_id: str
    customer_name: str
    customer_email: str | None = None
    project_type: str = "solar"
    system_size_kwp: float | None = None
    annual_yield_kwh: float | None = None
    quote_value_chf: float | None = None
    status: str = "draft"
    sent_at: datetime | None = None
    accepted_at: datetime | None = None
    rejected_at: datetime | None = None
    expires_at: datetime | None = None
    body_markdown: str | None = None
    email_message_id: str | None = None
    kama_net_quote_id: str | None = None
    notes: str | None = None


class SalesFollowupRow(BaseModel):
    id: uuid.UUID
    quote_id: uuid.UUID
    anfrage_kama_net_id: str
    scheduled_at: datetime
    sent_at: datetime | None = None
    status: str = "pending"
    attempt_number: int = 1
    email_message_id: str | None = None


# ─────────────────────────────────────────────────────────────────
# Domain objects
# ─────────────────────────────────────────────────────────────────


class SolarCalcResult(BaseModel):
    """Output of the solar offer calculator."""

    system_size_kwp: float
    annual_yield_kwh: float
    co2_savings_kg_per_year: float
    quote_value_chf: float
    payback_years: float
