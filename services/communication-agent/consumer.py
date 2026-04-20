"""Communication Agent — Kafka consumer + multi-channel communication orchestrator."""
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
from db import insert_message, insert_sop, update_sop_kama_net_id, upsert_thread
from email_handler import async_poll_inbox, async_send_email
from models import (
    CommMessageRow,
    CommSendRequest,
    CommSopRow,
    CommThreadRow,
    InternalTaskRequest,
    ProcurementDeliveredEvent,
    ProcurementOrderedEvent,
)
from paperclip_client import create_internal_task
from sop_writer import build_sop_body, save_sop_to_kama_net
from telegram_bot import notify_roman, poll_updates, send_telegram_message

log = structlog.get_logger()


class CommunicationAgent:
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
        topics = [
            settings.kafka_topic_comm_send,
            settings.kafka_topic_procurement_ordered,
            settings.kafka_topic_procurement_delivered,
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
            value_serializer=lambda v: json.dumps(v).encode(),
        )
        await self._consumer.start()
        await self._producer.start()
        self._running = True
        log.info("communication_agent_started", topics=topics)

    async def stop(self) -> None:
        self._running = False
        if self._consumer:
            await self._consumer.stop()
        if self._producer:
            await self._producer.stop()
        log.info(
            "communication_agent_stopped",
            received=self.total_received,
            processed=self.total_processed,
            errors=self.total_errors,
        )

    async def run(self) -> None:
        """Main loop: consume Kafka events and concurrently poll inbound channels."""
        assert self._consumer is not None

        inbound_task = asyncio.create_task(self._inbound_poll_loop())

        try:
            async for msg in self._consumer:
                await self._handle_kafka(msg)
                await self._consumer.commit()
        except asyncio.CancelledError:
            pass
        except KafkaError as exc:
            log.error("kafka_error", exc=str(exc))
            raise
        finally:
            inbound_task.cancel()
            try:
                await inbound_task
            except asyncio.CancelledError:
                pass

    # ─────────────────────────────────────────────────────────────
    # Inbound polling loop (email + telegram)
    # ─────────────────────────────────────────────────────────────

    async def _inbound_poll_loop(self) -> None:
        """Periodically poll IMAP and Telegram for inbound messages."""
        while self._running:
            await asyncio.sleep(settings.imap_poll_interval_sec)
            await self._process_inbound_email()
            await self._process_inbound_telegram()

    async def _process_inbound_email(self) -> None:
        try:
            rows = await async_poll_inbox()
        except Exception as exc:
            log.error("inbound_email_error", error=str(exc))
            return

        for row in rows:
            try:
                await insert_message(self._pool, row)
                await self._emit(
                    settings.kafka_topic_comm_reply,
                    {
                        "event": "comm.reply_received",
                        "channel": "email",
                        "sender": row.sender,
                        "subject": row.subject,
                        "external_id": row.external_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
                log.info("inbound_email_stored", sender=row.sender, subject=row.subject)
            except Exception as exc:
                log.error("inbound_email_store_error", error=str(exc))

    async def _process_inbound_telegram(self) -> None:
        try:
            rows = await poll_updates()
        except Exception as exc:
            log.error("inbound_telegram_error", error=str(exc))
            return

        for row in rows:
            try:
                await insert_message(self._pool, row)
                await self._emit(
                    settings.kafka_topic_comm_reply,
                    {
                        "event": "comm.reply_received",
                        "channel": "telegram",
                        "sender": row.sender,
                        "body": row.body,
                        "external_id": row.external_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
                log.info("inbound_telegram_stored", sender=row.sender)
            except Exception as exc:
                log.error("inbound_telegram_store_error", error=str(exc))

    # ─────────────────────────────────────────────────────────────
    # Kafka event dispatch
    # ─────────────────────────────────────────────────────────────

    async def _handle_kafka(self, msg: Any) -> None:
        self.total_received += 1
        try:
            payload = json.loads(msg.value)
        except json.JSONDecodeError as exc:
            self.total_errors += 1
            log.warning("invalid_json", error=str(exc), topic=msg.topic)
            return

        event_name = payload.get("event", "")
        try:
            if msg.topic == settings.kafka_topic_comm_send:
                await self._handle_send_request(payload)
            elif msg.topic == settings.kafka_topic_procurement_ordered:
                await self._handle_procurement_ordered(payload)
            elif msg.topic == settings.kafka_topic_procurement_delivered:
                await self._handle_procurement_delivered(payload)
            else:
                log.debug("unknown_topic", topic=msg.topic, event=event_name)
            self.total_processed += 1
        except Exception as exc:
            self.total_errors += 1
            log.error("event_handling_error", event=event_name, error=str(exc))

    # ─────────────────────────────────────────────────────────────
    # Handler: explicit send request from other agents
    # ─────────────────────────────────────────────────────────────

    async def _handle_send_request(self, payload: dict[str, Any]) -> None:
        try:
            req = CommSendRequest.model_validate(payload)
        except ValidationError as exc:
            log.warning("invalid_send_request", error=str(exc))
            return

        thread_id = uuid.UUID(req.thread_id) if req.thread_id else None

        if req.channel == "email":
            msg_id = await async_send_email(
                recipient=req.recipient,
                subject=req.subject or "(kein Betreff)",
                body=req.body,
            )
            row = CommMessageRow(
                channel="email",
                direction="outbound",
                external_id=msg_id,
                thread_id=thread_id,
                sender=settings.smtp_from,
                recipient=req.recipient,
                subject=req.subject,
                body=req.body,
                metadata=req.context,
                status="sent",
                sent_at=datetime.now(timezone.utc),
            )
            await insert_message(self._pool, row)

        elif req.channel == "telegram":
            tg_msg_id = await send_telegram_message(req.recipient, req.body)
            row = CommMessageRow(
                channel="telegram",
                direction="outbound",
                external_id=str(tg_msg_id) if tg_msg_id else None,
                thread_id=thread_id,
                sender="bot",
                recipient=req.recipient,
                body=req.body,
                metadata=req.context,
                status="sent",
                sent_at=datetime.now(timezone.utc),
            )
            await insert_message(self._pool, row)

        elif req.channel == "internal":
            task_req = InternalTaskRequest(
                trigger=req.context.get("trigger", "comm.send_request"),
                responsible=req.recipient,
                goal=req.subject or req.body[:80],
                expected_result=req.body,
                deadline_iso=req.context.get("deadline"),
                priority=req.context.get("priority", "medium"),
                context=req.context,
            )
            await create_internal_task(task_req)

        elif req.channel == "whatsapp":
            # WhatsApp integration is planned — log and skip for now
            log.info("whatsapp_send_planned", recipient=req.recipient, body=req.body[:60])
            return

        await self._emit(
            settings.kafka_topic_comm_sent,
            {
                "event": "comm.message_sent",
                "channel": req.channel,
                "recipient": req.recipient,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    # ─────────────────────────────────────────────────────────────
    # Handler: procurement-agent ordered materials
    # ─────────────────────────────────────────────────────────────

    async def _handle_procurement_ordered(self, payload: dict[str, Any]) -> None:
        try:
            event = ProcurementOrderedEvent.model_validate(payload)
        except ValidationError as exc:
            log.warning("invalid_procurement_ordered", error=str(exc))
            return

        suppliers_str = ", ".join(event.suppliers)
        text = (
            f"✅ *Bestellung ausgelöst*\n"
            f"Auftrag: `{event.auftrag_id}`\n"
            f"Lieferanten: {suppliers_str}"
        )
        await notify_roman(text)

        # Create thread to track delivery confirmations
        thread = CommThreadRow(
            channel="telegram",
            topic=f"Bestellung {event.auftrag_id}",
            participant=settings.telegram_roman_chat_id,
            awaiting_reply_from="supplier",
            context={"auftrag_id": event.auftrag_id, "suppliers": event.suppliers},
        )
        await upsert_thread(self._pool, thread)
        log.info("procurement_ordered_notified", auftrag_id=event.auftrag_id)

    # ─────────────────────────────────────────────────────────────
    # Handler: procurement-agent delivery arrived
    # ─────────────────────────────────────────────────────────────

    async def _handle_procurement_delivered(self, payload: dict[str, Any]) -> None:
        try:
            event = ProcurementDeliveredEvent.model_validate(payload)
        except ValidationError as exc:
            log.warning("invalid_procurement_delivered", error=str(exc))
            return

        text = (
            f"📦 *Lieferung eingetroffen*\n"
            f"Auftrag: `{event.auftrag_id}`\n"
            f"Lieferant: {event.supplier}"
        )
        await notify_roman(text)

        # Auto-generate a SOP for the delivery confirmation flow
        sop_body = build_sop_body(
            title=f"Wareneingang {event.supplier}",
            domain="logistics",
            trigger=f"Lieferung von {event.supplier} für Auftrag {event.auftrag_id}",
            steps=[
                "Lieferschein prüfen (Dropbox DIMEC)",
                "Artikelmengen gegen BOM abgleichen",
                "Wareneingangsmeldung in app_articles buchen",
                f"Produktions-Agent über vollständige Lieferung informieren",
                "Rechnung ablegen",
            ],
            responsible="Lager-Agent",
            notes=f"Auftrag {event.auftrag_id}, Lieferant {event.supplier}",
        )
        sop_row = CommSopRow(
            title=f"Wareneingang {event.supplier}",
            domain="logistics",
            body=sop_body,
        )
        sop_id = await insert_sop(self._pool, sop_row)
        kama_net_id = await save_sop_to_kama_net(sop_row)
        if kama_net_id:
            await update_sop_kama_net_id(self._pool, sop_id, kama_net_id)

        await self._emit(
            settings.kafka_topic_comm_sop,
            {
                "event": "comm.sop_created",
                "sop_id": str(sop_id),
                "domain": "logistics",
                "title": sop_row.title,
                "kama_net_id": kama_net_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        log.info(
            "delivery_notification_sent",
            auftrag_id=event.auftrag_id,
            sop_id=str(sop_id),
        )

    # ─────────────────────────────────────────────────────────────
    # Kafka emit helper
    # ─────────────────────────────────────────────────────────────

    async def _emit(self, topic: str, payload: dict[str, Any]) -> None:
        assert self._producer is not None
        await self._producer.send_and_wait(topic, payload)
        log.debug("kafka_event_emitted", topic=topic, event=payload.get("event"))
