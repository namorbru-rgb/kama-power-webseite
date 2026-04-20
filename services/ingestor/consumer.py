"""Kafka consumer loop — reads TelemetryEvent messages and batches them to DB."""
import asyncio
import json
import time
from typing import Any

import asyncpg
import structlog
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError
from pydantic import ValidationError

from config import settings
from db import batch_insert
from models import TelemetryEvent

log = structlog.get_logger()


class Ingestor:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
        self._batch: list[dict[str, Any]] = []
        self._last_flush = time.monotonic()
        self._consumer: AIOKafkaConsumer | None = None
        self._running = False

        # metrics (simple counters)
        self.total_received = 0
        self.total_inserted = 0
        self.total_invalid = 0

    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(
            settings.kafka_topic_telemetry,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=settings.kafka_group_id,
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            value_deserializer=lambda b: b,  # raw bytes; we parse manually
        )
        await self._consumer.start()
        self._running = True
        log.info(
            "consumer_started",
            topic=settings.kafka_topic_telemetry,
            group=settings.kafka_group_id,
        )

    async def stop(self) -> None:
        self._running = False
        if self._consumer:
            await self._flush()
            await self._consumer.stop()
        log.info("consumer_stopped")

    async def run(self) -> None:
        assert self._consumer is not None, "call start() first"
        try:
            async for msg in self._consumer:
                await self._handle(msg)
                # Flush if batch is full or timeout exceeded
                if (
                    len(self._batch) >= settings.batch_size
                    or time.monotonic() - self._last_flush
                    >= settings.batch_flush_interval_sec
                ):
                    await self._flush()
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
            event = TelemetryEvent.model_validate(payload)
            self._batch.append(event.to_db_row())
        except (json.JSONDecodeError, ValidationError) as exc:
            self.total_invalid += 1
            log.warning(
                "invalid_message",
                topic=msg.topic,
                partition=msg.partition,
                offset=msg.offset,
                error=str(exc),
            )

    async def _flush(self) -> None:
        if not self._batch:
            self._last_flush = time.monotonic()
            return
        batch, self._batch = self._batch, []
        try:
            inserted = await batch_insert(self._pool, batch)
            self.total_inserted += inserted
        except Exception as exc:
            log.error("flush_error", exc=str(exc), batch_size=len(batch))
            # Re-queue the failed batch so we don't lose records across a restart;
            # in production consider a DLQ Kafka topic instead.
            self._batch = batch + self._batch
        finally:
            self._last_flush = time.monotonic()
