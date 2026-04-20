"""Entrypoint for the grid-normalizer service.

Consumes raw grid signal events from Kafka, normalises them through
source-specific transformers, writes canonical GridSignal rows to
TimescaleDB, and re-publishes on the grid.normalized Kafka topic.
"""
from __future__ import annotations

import asyncio
import signal

import structlog

from consumer import GridNormalizerConsumer
from db import GridSignalWriter
from producer import NormalizedProducer

log = structlog.get_logger()


async def main() -> None:
    log.info("grid_normalizer_starting")

    consumer = GridNormalizerConsumer()
    producer = NormalizedProducer()
    writer = GridSignalWriter()

    await consumer.start()
    await producer.start()
    writer.connect()

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _handle_signal() -> None:
        log.info("shutdown_signal_received")
        stop_event.set()

    loop.add_signal_handler(signal.SIGTERM, _handle_signal)
    loop.add_signal_handler(signal.SIGINT, _handle_signal)

    async def _run() -> None:
        async for batch in consumer.consume():
            # Write to DB in thread pool to keep event loop free
            await asyncio.to_thread(writer.write_batch, batch)
            await producer.publish(batch)

    run_task = asyncio.create_task(_run())
    await stop_event.wait()

    run_task.cancel()
    try:
        await run_task
    except asyncio.CancelledError:
        pass

    await consumer.stop()
    await producer.stop()
    writer.close()
    log.info("grid_normalizer_stopped")


if __name__ == "__main__":
    asyncio.run(main())
