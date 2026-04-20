"""KAMA Procurement Agent — Kafka → BOM → Inventory → Supplier Orders → TimescaleDB."""
import asyncio
import signal

import structlog

from config import settings
from consumer import ProcurementAgent
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
        "procurement_agent_starting",
        kafka=settings.kafka_bootstrap_servers,
        topic_in=settings.kafka_topic_orders_confirmed,
        topic_out_ordered=settings.kafka_topic_procurement_ordered,
    )

    pool = await create_pool(settings.database_url)
    agent = ProcurementAgent(pool)
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
            "procurement_agent_stopped",
            received=agent.total_received,
            processed=agent.total_processed,
            errors=agent.total_errors,
        )


if __name__ == "__main__":
    asyncio.run(main())
