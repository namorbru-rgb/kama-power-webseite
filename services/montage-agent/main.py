"""KAMA Montage Agent — Montageaufträge, Ressourcen, Fortschritt, Abnahmeprotokoll."""
import asyncio
import signal

import structlog

from config import settings
from consumer import MontageAgent
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
        "montage_agent_starting",
        kafka=settings.kafka_bootstrap_servers,
        topic_orders=settings.kafka_topic_orders_confirmed,
        topic_delivery=settings.kafka_topic_procurement_delivered,
        topic_progress=settings.kafka_topic_montage_progress,
        assignment_strategy=settings.assignment_strategy,
    )

    pool = await create_pool(settings.database_url)
    agent = MontageAgent(pool)
    await agent.start()

    loop = asyncio.get_running_loop()
    task = loop.create_task(agent.run())

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
        await agent.stop()
        await pool.close()
        log.info(
            "montage_agent_stopped",
            received=agent.total_received,
            processed=agent.total_processed,
            errors=agent.total_errors,
        )


if __name__ == "__main__":
    asyncio.run(main())
