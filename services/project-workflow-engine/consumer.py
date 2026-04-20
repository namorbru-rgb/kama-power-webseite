"""Projekt- & Workflow-Engine — multi-topic Kafka consumer."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

import asyncpg
import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.errors import KafkaError
from pydantic import ValidationError

from config import settings
from engine import WorkflowEngine
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

    async def stop(self) -> None:
        self._running = False
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
