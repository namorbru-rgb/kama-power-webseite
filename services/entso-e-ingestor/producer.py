"""Kafka producer for normalized grid signals."""
from __future__ import annotations

import json
from datetime import datetime

import structlog
from aiokafka import AIOKafkaProducer

from config import settings

log = structlog.get_logger()


def _json_default(obj: object) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Cannot serialize {type(obj)!r}")


class GridProducer:
    def __init__(self) -> None:
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, default=_json_default).encode(),
        )
        await self._producer.start()
        log.info("grid_producer_started", topic=settings.kafka_topic_grid)

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()
        log.info("grid_producer_stopped")

    async def publish(self, signals: list[dict]) -> None:
        assert self._producer is not None, "call start() first"
        for signal in signals:
            await self._producer.send(settings.kafka_topic_grid, value=signal)
        log.info("grid_published", topic=settings.kafka_topic_grid, count=len(signals))
