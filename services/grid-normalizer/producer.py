"""Kafka producer — publishes canonical GridSignal messages to grid.normalized."""
from __future__ import annotations

import json
from datetime import datetime

import structlog
from aiokafka import AIOKafkaProducer

from config import settings
from models import GridSignal

log = structlog.get_logger()


def _json_default(obj: object) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Cannot serialize {type(obj)!r}")


class NormalizedProducer:
    def __init__(self) -> None:
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, default=_json_default).encode(),
        )
        await self._producer.start()
        log.info("normalized_producer_started", topic=settings.kafka_topic_normalized)

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()
        log.info("normalized_producer_stopped")

    async def publish(self, signals: list[GridSignal]) -> None:
        assert self._producer is not None, "call start() first"
        for signal in signals:
            await self._producer.send(
                settings.kafka_topic_normalized,
                value=signal.to_kafka_dict(),
            )
        log.info(
            "normalized_published",
            topic=settings.kafka_topic_normalized,
            count=len(signals),
        )
