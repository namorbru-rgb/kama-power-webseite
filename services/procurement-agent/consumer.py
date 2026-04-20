"""Procurement Agent — Kafka consumer + procurement workflow."""
from __future__ import annotations

import asyncio
import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import asyncpg
import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.errors import KafkaError
from pydantic import ValidationError

from bom import fetch_bom
from config import settings
from db import insert_order, mark_order_sent, upsert_bom
from inventory import compute_deltas, fetch_stock
from mailer import send_order_email
from models import (
    DeltaItem,
    OrderConfirmedEvent,
    ProcurementOrderItemRow,
    ProcurementOrderRow,
    SupplierOrder,
)

log = structlog.get_logger()


class ProcurementAgent:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
        self._consumer: AIOKafkaConsumer | None = None
        self._producer: AIOKafkaProducer | None = None
        self._running = False

        self.total_received = 0
        self.total_processed = 0
        self.total_errors = 0

    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(
            settings.kafka_topic_orders_confirmed,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=settings.kafka_group_id,
            auto_offset_reset="earliest",
            enable_auto_commit=False,
        )
        self._producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode(),
        )
        await self._consumer.start()
        await self._producer.start()
        self._running = True
        log.info(
            "procurement_agent_started",
            topic=settings.kafka_topic_orders_confirmed,
            group=settings.kafka_group_id,
        )

    async def stop(self) -> None:
        self._running = False
        if self._consumer:
            await self._consumer.stop()
        if self._producer:
            await self._producer.stop()
        log.info(
            "procurement_agent_stopped",
            received=self.total_received,
            processed=self.total_processed,
            errors=self.total_errors,
        )

    async def run(self) -> None:
        assert self._consumer is not None
        try:
            async for msg in self._consumer:
                await self._handle(msg)
                await self._consumer.commit()
        except asyncio.CancelledError:
            pass
        except KafkaError as exc:
            log.error("kafka_error", exc=str(exc))
            raise

    async def _handle(self, msg: Any) -> None:
        self.total_received += 1
        try:
            payload = json.loads(msg.value)
            event = OrderConfirmedEvent.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            self.total_errors += 1
            log.warning("invalid_event", error=str(exc))
            return

        log.info("processing_order", auftrag_id=event.auftrag_id)

        try:
            await self._process_order(event)
            self.total_processed += 1
        except Exception as exc:
            self.total_errors += 1
            log.error("processing_error", auftrag_id=event.auftrag_id, error=str(exc))

    async def _process_order(self, event: OrderConfirmedEvent) -> None:
        # Step 1 — Load BOM
        bom = await fetch_bom(event.auftrag_id, event.system_size_kwp)
        if not bom:
            log.warning("no_bom_items", auftrag_id=event.auftrag_id)
            return

        await upsert_bom(self._pool, event.auftrag_id, [b.model_dump() for b in bom])

        # Step 2 — Check inventory
        article_ids = [b.article_id for b in bom]
        stock = await fetch_stock(article_ids)

        # Step 3 — Compute deltas
        deltas = compute_deltas(bom, stock)
        if not deltas:
            log.info("all_articles_in_stock", auftrag_id=event.auftrag_id)
            return

        # Group by supplier
        by_supplier: dict[str, list[DeltaItem]] = defaultdict(list)
        for delta in deltas:
            by_supplier[delta.supplier].append(delta)

        # Step 4/5 — Send orders + persist
        for supplier, items in by_supplier.items():
            supplier_order = SupplierOrder(
                auftrag_id=event.auftrag_id, supplier=supplier, items=items
            )
            await self._place_order(supplier_order, event.customer_name)

        # Step 6 — Emit downstream event
        await self._emit_ordered_event(event.auftrag_id, list(by_supplier.keys()))

    async def _place_order(self, order: SupplierOrder, customer_name: str) -> None:
        order_id = uuid.uuid4()
        order_row = ProcurementOrderRow(
            id=order_id,
            auftrag_id=order.auftrag_id,
            supplier=order.supplier,
            status="draft",
        )
        item_rows = [
            ProcurementOrderItemRow(
                order_id=order_id,
                article_id=i.article_id,
                article_name=i.article_name,
                qty_ordered=i.qty_to_order,
                unit_price_chf=i.ek_price_chf,
                unit=i.unit,
            )
            for i in order.items
        ]

        await insert_order(self._pool, order_row, item_rows)

        # Send email
        message_id, expected_delivery = send_order_email(
            order.auftrag_id, order.supplier, order.items, customer_name
        )

        await mark_order_sent(self._pool, order_id, message_id, expected_delivery)

    async def _emit_ordered_event(self, auftrag_id: str, suppliers: list[str]) -> None:
        assert self._producer is not None
        payload = {
            "event": "procurement.ordered",
            "auftrag_id": auftrag_id,
            "suppliers": suppliers,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self._producer.send_and_wait(
            settings.kafka_topic_procurement_ordered, payload
        )
        log.info("procurement_ordered_event_sent", auftrag_id=auftrag_id, suppliers=suppliers)
