"""Lager & Logistik Agent — Kafka consumer + warehouse workflow orchestrator."""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import asyncpg
import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.errors import KafkaError
from pydantic import ValidationError

from config import settings
from db import (
    create_pool,
    get_lieferung_by_order,
    get_oldest_pending_eingetroffen,
    get_eingang_positionen,
    insert_eingang_position,
    insert_lieferung,
    update_lieferung_status,
    upsert_bestand,
)
from inventory import fetch_warehouse_employees, update_kama_net_stock
from models import (
    CommReplyEvent,
    CommSendRequest,
    LagerBestandRow,
    LagerEingangPositionRow,
    LagerLieferungRow,
    ProcurementDeliveredEvent,
    ProcurementOrderedEvent,
)

log = structlog.get_logger()

# Keywords that count as a "yes, goods received" confirmation
_CONFIRMATION_KEYWORDS: list[str] = []


def _load_confirmation_keywords() -> list[str]:
    global _CONFIRMATION_KEYWORDS
    _CONFIRMATION_KEYWORDS = [
        kw.strip().lower()
        for kw in settings.confirmation_keywords.split(",")
        if kw.strip()
    ]
    return _CONFIRMATION_KEYWORDS


def _is_confirmation(text: str) -> bool:
    lower = text.lower().strip()
    return any(kw in lower for kw in _CONFIRMATION_KEYWORDS)


class LagerLogistikAgent:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
        self._consumer: AIOKafkaConsumer | None = None
        self._producer: AIOKafkaProducer | None = None
        self._running = False

        self.total_received = 0
        self.total_processed = 0
        self.total_errors = 0

    # ─────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        _load_confirmation_keywords()

        topics = [
            settings.kafka_topic_procurement_ordered,
            settings.kafka_topic_procurement_delivered,
            settings.kafka_topic_comm_reply,
        ]
        self._consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=settings.kafka_group_id,
            auto_offset_reset="earliest",
            enable_auto_commit=False,
        )
        self._producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, default=str).encode(),
        )
        await self._consumer.start()
        await self._producer.start()
        self._running = True
        log.info(
            "lager_logistik_agent_started",
            topics=topics,
            group=settings.kafka_group_id,
        )

    async def stop(self) -> None:
        self._running = False
        if self._consumer:
            await self._consumer.stop()
        if self._producer:
            await self._producer.stop()
        log.info(
            "lager_logistik_agent_stopped",
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

    # ─────────────────────────────────────────────────────────────
    # Dispatch
    # ─────────────────────────────────────────────────────────────

    async def _handle(self, msg: Any) -> None:
        self.total_received += 1
        try:
            payload = json.loads(msg.value)
        except json.JSONDecodeError as exc:
            self.total_errors += 1
            log.warning("invalid_json", topic=msg.topic, error=str(exc))
            return

        try:
            if msg.topic == settings.kafka_topic_procurement_ordered:
                await self._handle_procurement_ordered(payload)
            elif msg.topic == settings.kafka_topic_procurement_delivered:
                await self._handle_procurement_delivered(payload)
            elif msg.topic == settings.kafka_topic_comm_reply:
                await self._handle_comm_reply(payload)
            else:
                log.debug("unknown_topic", topic=msg.topic)
            self.total_processed += 1
        except Exception as exc:
            self.total_errors += 1
            log.error(
                "event_handling_error",
                topic=msg.topic,
                error=str(exc),
                exc_info=True,
            )

    # ─────────────────────────────────────────────────────────────
    # Handler: procurement.ordered → advance notification
    # ─────────────────────────────────────────────────────────────

    async def _handle_procurement_ordered(self, payload: dict[str, Any]) -> None:
        try:
            event = ProcurementOrderedEvent.model_validate(payload)
        except ValidationError as exc:
            log.warning("invalid_procurement_ordered", error=str(exc))
            return

        auftrag_id = event.auftrag_id
        suppliers = ", ".join(event.suppliers) if event.suppliers else "Lieferant"

        log.info("procurement_ordered_received", auftrag_id=auftrag_id, suppliers=suppliers)

        # Create a placeholder delivery record (order_id not yet known)
        # Use a synthetic order_id based on auftrag + timestamp
        synthetic_order_id = f"advance_{auftrag_id}_{int(datetime.now(timezone.utc).timestamp())}"

        now = datetime.now(timezone.utc)
        row = LagerLieferungRow(
            auftrag_id=auftrag_id,
            order_id=synthetic_order_id,
            supplier=suppliers,
            status="geplant",
        )
        await insert_lieferung(self._pool, row)

        # Notify warehouse employees: "Lieferung geplant — Rampe vorbereiten"
        employees = await fetch_warehouse_employees()
        body = (
            f"📦 *Bestellung aufgegeben* — Auftrag `{auftrag_id}`\n"
            f"Lieferant(en): {suppliers}\n\n"
            f"Bitte Rampe und Lagerplatz vorbereiten. "
            f"Die Lieferung wird in den nächsten Tagen erwartet."
        )

        sent = False
        for emp in employees:
            if emp.telegram_chat_id:
                req = CommSendRequest(
                    channel="telegram",
                    recipient=emp.telegram_chat_id,
                    body=body,
                    context={
                        "auftrag_id": auftrag_id,
                        "lieferung_id": str(row.id),
                        "event": "procurement.ordered",
                    },
                )
                await self._emit(settings.kafka_topic_comm_send, req.model_dump())
                sent = True

        if sent:
            await update_lieferung_status(
                self._pool,
                str(row.id),
                "angekuendigt",
                vorankuendigung_sent_at=now,
            )
            log.info(
                "vorankuendigung_sent",
                auftrag_id=auftrag_id,
                employees=len(employees),
            )
        else:
            log.warning(
                "no_warehouse_employees_configured",
                auftrag_id=auftrag_id,
            )

    # ─────────────────────────────────────────────────────────────
    # Handler: procurement.delivered → goods arrived
    # ─────────────────────────────────────────────────────────────

    async def _handle_procurement_delivered(self, payload: dict[str, Any]) -> None:
        try:
            event = ProcurementDeliveredEvent.model_validate(payload)
        except ValidationError as exc:
            log.warning("invalid_procurement_delivered", error=str(exc))
            return

        log.info(
            "procurement_delivered_received",
            auftrag_id=event.auftrag_id,
            order_id=event.order_id,
            supplier=event.supplier,
        )

        now = datetime.now(timezone.utc)

        # Check if we already have a record for this order
        existing = await get_lieferung_by_order(self._pool, event.order_id)
        if existing:
            lieferung_id = str(existing["id"])
            await update_lieferung_status(
                self._pool,
                lieferung_id,
                "eingetroffen",
                eingang_at=now,
            )
        else:
            # Create new record (procurement.ordered may have used a synthetic id)
            row = LagerLieferungRow(
                auftrag_id=event.auftrag_id,
                order_id=event.order_id,
                supplier=event.supplier,
                status="eingetroffen",
                eingang_at=now,
            )
            await insert_lieferung(self._pool, row)
            lieferung_id = str(row.id)

        # Notify warehouse employees to inspect and confirm
        employees = await fetch_warehouse_employees()
        body = (
            f"🚛 *Lieferung angekommen!* — Auftrag `{event.auftrag_id}`\n"
            f"Lieferant: {event.supplier}\n\n"
            f"Bitte Waren prüfen und mit *JA* oder *bestätigt* antworten, "
            f"wenn alles vollständig ist. Bei Abweichungen kurz beschreiben."
        )

        sent = False
        for emp in employees:
            if emp.telegram_chat_id:
                req = CommSendRequest(
                    channel="telegram",
                    recipient=emp.telegram_chat_id,
                    body=body,
                    context={
                        "auftrag_id": event.auftrag_id,
                        "order_id": event.order_id,
                        "lieferung_id": lieferung_id,
                        "event": "procurement.delivered",
                        "expects_reply": True,
                    },
                )
                await self._emit(settings.kafka_topic_comm_send, req.model_dump())
                sent = True

        if sent:
            await update_lieferung_status(
                self._pool,
                lieferung_id,
                "eingetroffen",
                eingang_at=now,
                eingang_notification_sent_at=now,
            )
            log.info(
                "eingang_notification_sent",
                auftrag_id=event.auftrag_id,
                lieferung_id=lieferung_id,
                employees=len(employees),
            )
        else:
            log.warning(
                "no_warehouse_employees_for_delivery",
                auftrag_id=event.auftrag_id,
            )

    # ─────────────────────────────────────────────────────────────
    # Handler: comm.reply_received → employee confirmation
    # ─────────────────────────────────────────────────────────────

    async def _handle_comm_reply(self, payload: dict[str, Any]) -> None:
        try:
            event = CommReplyEvent.model_validate(payload)
        except ValidationError as exc:
            log.warning("invalid_comm_reply", error=str(exc))
            return

        text = event.body or event.subject or ""
        if not _is_confirmation(text):
            log.debug(
                "comm_reply_not_a_confirmation",
                sender=event.sender,
                body=text[:80],
            )
            return

        # Find the oldest delivery waiting for confirmation (FIFO)
        pending = await get_oldest_pending_eingetroffen(self._pool)
        if not pending:
            log.debug("no_pending_delivery_for_confirmation", sender=event.sender)
            return

        lieferung_id = str(pending["id"])
        auftrag_id = pending["auftrag_id"]
        now = datetime.now(timezone.utc)

        log.info(
            "goods_receipt_confirmed",
            sender=event.sender,
            lieferung_id=lieferung_id,
            auftrag_id=auftrag_id,
        )

        # Mark delivery as confirmed
        await update_lieferung_status(
            self._pool,
            lieferung_id,
            "bestaetigt",
            bestaetigt_at=now,
            bestaetigt_by=event.sender,
        )

        # Update inventory for each position of this delivery
        positions = await get_eingang_positionen(self._pool, lieferung_id)
        updated_articles: list[dict] = []
        for pos in positions:
            # Update local DB inventory
            bestand_row = LagerBestandRow(
                article_id=pos["article_id"],
                article_name=pos["article_name"],
                qty=pos["qty_received"],
                unit=pos["unit"],
                last_eingang_at=now,
            )
            await upsert_bestand(self._pool, bestand_row)

            # Update KAMA-net stock
            await update_kama_net_stock(
                pos["article_id"], pos["qty_received"], pos["unit"]
            )

            updated_articles.append({
                "article_id": pos["article_id"],
                "article_name": pos["article_name"],
                "qty_received": pos["qty_received"],
                "unit": pos["unit"],
            })

        # Emit lager.eingang_bestaetigt — triggers Montage Agent / production release
        await self._emit(
            settings.kafka_topic_lager_eingang,
            {
                "event": "lager.eingang_bestaetigt",
                "lieferung_id": lieferung_id,
                "auftrag_id": auftrag_id,
                "supplier": pending["supplier"],
                "bestaetigt_by": event.sender,
                "bestaetigt_at": now.isoformat(),
                "articles": updated_articles,
                "timestamp": now.isoformat(),
            },
        )

        # Emit lager.bestand_aktualisiert for dashboards
        if updated_articles:
            await self._emit(
                settings.kafka_topic_lager_bestand,
                {
                    "event": "lager.bestand_aktualisiert",
                    "lieferung_id": lieferung_id,
                    "auftrag_id": auftrag_id,
                    "articles": updated_articles,
                    "timestamp": now.isoformat(),
                },
            )

        # Send acknowledgment to the employee who confirmed
        employees = await fetch_warehouse_employees()
        sender_employee = next(
            (e for e in employees if e.telegram_chat_id == event.sender),
            None,
        )
        if sender_employee or event.channel == "telegram":
            recipient = event.sender
            ack_body = (
                f"✅ *Wareneingang bestätigt* — Auftrag `{auftrag_id}`\n"
                f"Lagerbestand wurde aktualisiert. Danke!"
            )
            req = CommSendRequest(
                channel="telegram",
                recipient=recipient,
                body=ack_body,
                context={
                    "auftrag_id": auftrag_id,
                    "lieferung_id": lieferung_id,
                    "event": "lager.eingang_bestaetigt",
                },
            )
            await self._emit(settings.kafka_topic_comm_send, req.model_dump())

        log.info(
            "lager_eingang_completed",
            auftrag_id=auftrag_id,
            lieferung_id=lieferung_id,
            articles_updated=len(updated_articles),
        )

    # ─────────────────────────────────────────────────────────────
    # Kafka emit helper
    # ─────────────────────────────────────────────────────────────

    async def _emit(self, topic: str, payload: dict[str, Any]) -> None:
        assert self._producer is not None
        await self._producer.send_and_wait(topic, payload)
        log.debug("kafka_emitted", topic=topic, event=payload.get("event"))
