"""Projekt- & Workflow-Engine — multi-topic Kafka consumer."""
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
from engine import WorkflowEngine
from imap_inbound import async_poll_inbox
import memory_store
from models import (
    MontageCompletedEvent,
    OrderConfirmedEvent,
    ProcurementDeliveredEvent,
)

log = structlog.get_logger()

# Inbound topics and the event key that identifies them
_TOPICS = [
    settings.kafka_topic_orders_confirmed,
    settings.kafka_topic_procurement_delivered,
    settings.kafka_topic_montage_completed,
]


class WorkflowConsumer:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
        self._consumer: AIOKafkaConsumer | None = None
        self._producer: AIOKafkaProducer | None = None
        self._engine: WorkflowEngine | None = None
        self._running = False

        self.total_received = 0
        self.total_processed = 0
        self.total_errors = 0

    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(
            *_TOPICS,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=settings.kafka_group_id,
            auto_offset_reset="earliest",
            enable_auto_commit=False,
        )
        self._producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: v,   # engine passes pre-encoded bytes
        )
        await self._consumer.start()
        await self._producer.start()
        self._engine = WorkflowEngine(self._pool, self._producer)
        self._running = True
        log.info(
            "workflow_consumer_started",
            topics=_TOPICS,
            group=settings.kafka_group_id,
        )

        # --- Memory read hook (run start) ---
        if settings.agent_memory_enabled:
            prior = await memory_store.read_memory(
                supabase_url=settings.kama_net_url,
                service_role_key=settings.supabase_service_role_key,
                agent_id=settings.agent_memory_agent_id,
                scope=settings.agent_memory_scope,
                limit=settings.agent_memory_read_limit,
            )
            if prior:
                log.info(
                    "agent_memory_context_loaded",
                    items=len(prior),
                    top_summary=prior[0].get("summary", "") if prior else "",
                )

    async def stop(self) -> None:
        self._running = False

        # --- Memory write hook (run end) ---
        if settings.agent_memory_enabled:
            summary = (
                f"Run ended: received={self.total_received} "
                f"processed={self.total_processed} errors={self.total_errors}"
            )
            await memory_store.write_memory_item(
                supabase_url=settings.kama_net_url,
                service_role_key=settings.supabase_service_role_key,
                agent_id=settings.agent_memory_agent_id,
                kind="run_summary",
                summary=summary,
                scope=settings.agent_memory_scope,
                details_json={
                    "total_received": self.total_received,
                    "total_processed": self.total_processed,
                    "total_errors": self.total_errors,
                },
                importance=3,
            )
            await memory_store.write_snapshot(
                supabase_url=settings.kama_net_url,
                service_role_key=settings.supabase_service_role_key,
                agent_id=settings.agent_memory_agent_id,
                summary=summary,
                scope=settings.agent_memory_scope,
                items_json={
                    "total_received": self.total_received,
                    "total_processed": self.total_processed,
                    "total_errors": self.total_errors,
                },
            )

        if self._consumer:
            await self._consumer.stop()
        if self._producer:
            await self._producer.stop()
        log.info(
            "workflow_consumer_stopped",
            received=self.total_received,
            processed=self.total_processed,
            errors=self.total_errors,
        )

    async def run(self) -> None:
        assert self._consumer is not None
        inbound_task = asyncio.create_task(self._inbound_email_loop())
        try:
            async for msg in self._consumer:
                await self._handle(msg)
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

    async def _handle(self, msg: Any) -> None:
        self.total_received += 1
        topic = msg.topic

        try:
            payload = json.loads(msg.value)
        except json.JSONDecodeError as exc:
            self.total_errors += 1
            log.warning("json_decode_error", topic=topic, error=str(exc))
            return

        try:
            await self._dispatch(topic, payload)
            self.total_processed += 1
        except Exception as exc:
            self.total_errors += 1
            log.error("dispatch_error", topic=topic, error=str(exc))

    async def _dispatch(self, topic: str, payload: dict[str, Any]) -> None:
        assert self._engine is not None

        if topic == settings.kafka_topic_orders_confirmed:
            event = OrderConfirmedEvent.model_validate(payload)
            await self._engine.on_order_confirmed(event)

        elif topic == settings.kafka_topic_procurement_delivered:
            event = ProcurementDeliveredEvent.model_validate(payload)
            await self._engine.on_procurement_delivered(event)

        elif topic == settings.kafka_topic_montage_completed:
            event = MontageCompletedEvent.model_validate(payload)
            await self._engine.on_montage_completed(event)

        else:
            log.warning("unknown_topic", topic=topic)

    async def _inbound_email_loop(self) -> None:
        while self._running:
            try:
                await self._process_inbound_email()
            except Exception as exc:
                log.error("ops_inbound_email_loop_error", error=str(exc), exc_info=True)
            await asyncio.sleep(settings.imap_poll_interval_sec)

    async def _process_inbound_email(self) -> None:
        rows = await async_poll_inbox()
        for row in rows:
            message_id = row["message_id"] or f"<ops-{uuid.uuid4()}@kama-power.com>"
            ops_event = {
                "event": "ops.inbound_email",
                "message_id": message_id,
                "in_reply_to": row["in_reply_to"],
                "channel": "email",
                "sender_email": row["sender_email"],
                "subject": row["subject"],
                "body": row["body"],
                "received_at": row["received_at"],
                "context": {"mailbox": settings.imap_user},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await self._emit(settings.kafka_topic_ops_inbound_email, ops_event)

            # Route into central comm reply topic for shared downstream handling.
            await self._emit(
                settings.kafka_topic_comm_reply,
                {
                    "event": "comm.reply_received",
                    "message_id": message_id,
                    "in_reply_to": row["in_reply_to"],
                    "channel": "email",
                    "sender_email": row["sender_email"],
                    "body": row["body"],
                    "received_at": row["received_at"],
                    "context": {
                        "source_service": "project-workflow-engine",
                        "mailbox": settings.imap_user,
                        "subject": row["subject"],
                    },
                },
            )
            log.info(
                "ops_inbound_email_received",
                sender=row["sender_email"],
                subject=row["subject"],
            )

    async def _emit(self, topic: str, payload: dict[str, Any]) -> None:
        assert self._producer is not None
        await self._producer.send_and_wait(topic, json.dumps(payload, default=str).encode())
        log.debug("kafka_emitted", topic=topic, event=payload.get("event"))
