"""Kafka consumer — reads raw grid signal topics and dispatches to transformers."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

import structlog
from aiokafka import AIOKafkaConsumer

from config import settings
from models import GridSignal
from transformers import entso_e

log = structlog.get_logger()


class GridNormalizerConsumer:
    def __init__(self) -> None:
        self._consumer: AIOKafkaConsumer | None = None

    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(
            settings.kafka_topic_entso_e_raw,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=settings.kafka_group_id,
            value_deserializer=lambda v: json.loads(v.decode()),
            auto_offset_reset="earliest",
            enable_auto_commit=False,
        )
        await self._consumer.start()
        log.info(
            "grid_normalizer_consumer_started",
            topics=[settings.kafka_topic_entso_e_raw],
        )

    async def stop(self) -> None:
        if self._consumer:
            await self._consumer.stop()
        log.info("grid_normalizer_consumer_stopped")

    async def consume(self) -> AsyncIterator[list[GridSignal]]:
        """Yield batches of canonical GridSignal objects.

        Batches are flushed when `batch_size` messages accumulate or the
        Kafka fetch returns an empty poll (idle partition).
        """
        assert self._consumer is not None, "call start() first"
        batch: list[GridSignal] = []

        async for msg in self._consumer:
            try:
                raw: dict = msg.value  # already deserialized
                signal = entso_e.transform(raw)
                batch.append(signal)
            except (KeyError, ValueError, TypeError) as exc:
                log.warning(
                    "transform_skipped",
                    topic=msg.topic,
                    offset=msg.offset,
                    error=str(exc),
                )
                continue

            if len(batch) >= settings.batch_size:
                yield batch
                await self._consumer.commit()
                batch = []

        # Flush remainder on clean shutdown
        if batch:
            yield batch
            await self._consumer.commit()
