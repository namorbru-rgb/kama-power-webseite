"""KAMA Telemetry Ingestor — Kafka → TimescaleDB."""
import asyncio
import signal

import structlog

from config import settings
from consumer import Ingestor
from db import create_pool

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)

log = structlog.get_logger()


async def main() -> None:
    log.info(
        "ingestor_starting",
        kafka=settings.kafka_bootstrap_servers,
        topic=settings.kafka_topic_telemetry,
    )

    pool = await create_pool(settings.database_url)
    ingestor = Ingestor(pool)
    await ingestor.start()

    loop = asyncio.get_running_loop()
    task = loop.create_task(ingestor.run())

    def _shutdown(sig: signal.Signals) -> None:
        log.info("shutdown_signal", sig=sig.name)
        task.cancel()

    for s in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(s, _shutdown, s)

    try:
        await task
    except asyncio.CancelledError:
        pass
    finally:
        await ingestor.stop()
        await pool.close()
        log.info(
            "ingestor_stopped",
            received=ingestor.total_received,
            inserted=ingestor.total_inserted,
            invalid=ingestor.total_invalid,
        )


if __name__ == "__main__":
    asyncio.run(main())
