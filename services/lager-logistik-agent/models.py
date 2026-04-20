"""Lager & Logistik Agent — domain models."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Kafka event models (inbound) ──────────────────────────────────────────────


class ProcurementOrderedEvent(BaseModel):
    """Consumed from kama.procurement.ordered."""

    event: str
    auftrag_id: str
    suppliers: list[str] = Field(default_factory=list)
    timestamp: str


class ProcurementDeliveredEvent(BaseModel):
    """Consumed from kama.procurement.delivered — goods arrived."""

    event: str
    auftrag_id: str
    order_id: str
    supplier: str
    timestamp: str


class CommReplyEvent(BaseModel):
    """Consumed from kama.comm.reply_received — employee reply."""

    event: str
    channel: Literal["telegram", "email", "whatsapp", "internal"]
    sender: str
    body: str = ""
    subject: str | None = None
    external_id: str | None = None
    timestamp: str


# ── Kafka event models (outbound) ─────────────────────────────────────────────


class CommSendRequest(BaseModel):
    """Published to kama.comm.send_request for the Communication Agent."""

    event: Literal["comm.send_request"] = "comm.send_request"
    channel: Literal["telegram", "email", "whatsapp", "internal"]
    recipient: str
    subject: str | None = None
    body: str
    context: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# ── KAMA-net models ───────────────────────────────────────────────────────────


class WarehouseEmployee(BaseModel):
    """Warehouse employee contact loaded from config or KAMA-net."""

    name: str
    telegram_chat_id: str | None = None
    phone: str | None = None


class ArticleStock(BaseModel):
    """Stock line from KAMA-net app_articles."""

    article_id: str
    article_name: str
    stock_qty: float
    unit: str = "Stk"


# ── DB row models ─────────────────────────────────────────────────────────────


class LagerLieferungRow(BaseModel):
    """Row in lager_lieferungen."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    auftrag_id: str
    order_id: str
    supplier: str = ""
    # geplant → angekuendigt → eingetroffen → bestaetigt
    status: str = "geplant"
    expected_delivery: date | None = None
    eingang_at: datetime | None = None
    bestaetigt_at: datetime | None = None
    bestaetigt_by: str | None = None
    vorankuendigung_sent_at: datetime | None = None
    eingang_notification_sent_at: datetime | None = None
    notes: str | None = None


class LagerBestandRow(BaseModel):
    """Row in lager_bestand."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    article_id: str
    article_name: str = ""
    qty: float = 0.0
    unit: str = "Stk"
    last_eingang_at: datetime | None = None


class LagerEingangPositionRow(BaseModel):
    """Row in lager_eingang_positionen."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    lieferung_id: uuid.UUID
    article_id: str
    article_name: str = ""
    qty_received: float = 0.0
    unit: str = "Stk"
