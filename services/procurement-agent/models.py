"""Procurement Agent — domain models."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


# ── Kafka event models ────────────────────────────────────────────────────────

class OrderConfirmedEvent(BaseModel):
    """Consumed from kama.orders.confirmed."""
    event: str = "order.confirmed"
    auftrag_id: str
    project_type: Literal["solar", "bess", "vzev", "combined"] = "solar"
    system_size_kwp: float | None = None
    customer_name: str = ""


# ── KAMA-net / Supabase response models ──────────────────────────────────────

class BomItem(BaseModel):
    """Single BOM line from KAMA-net app_bom or default catalog."""
    article_id: str
    article_name: str
    qty_required: float
    unit: str = "Stk"


class ArticleStock(BaseModel):
    """Stock entry from KAMA-net app_articles."""
    article_id: str
    article_name: str
    stock_qty: float
    unit: str = "Stk"
    ek_price_chf: float | None = None


# ── Internal domain ───────────────────────────────────────────────────────────

class DeltaItem(BaseModel):
    """Article that needs to be ordered (required - stock > 0)."""
    article_id: str
    article_name: str
    qty_to_order: float
    unit: str = "Stk"
    ek_price_chf: float | None = None
    supplier: str  # assigned by supplier catalog


class SupplierOrder(BaseModel):
    """One order grouping for a single supplier."""
    auftrag_id: str
    supplier: str
    items: list[DeltaItem] = Field(default_factory=list)


# ── DB row models ─────────────────────────────────────────────────────────────

class ProcurementOrderRow(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    auftrag_id: str
    supplier: str
    status: str = "draft"
    ordered_at: datetime | None = None
    expected_delivery: date | None = None
    email_message_id: str | None = None
    notes: str | None = None


class ProcurementOrderItemRow(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    order_id: uuid.UUID
    article_id: str
    article_name: str
    qty_ordered: float
    unit_price_chf: float | None = None
    unit: str = "Stk"
