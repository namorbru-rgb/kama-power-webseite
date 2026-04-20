"""KAMA Projekt- & Workflow-Engine — entry point."""
import asyncio
import signal

import structlog

import paperclip_client as pc
from config import settings
from consumer import WorkflowConsumer
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
        "project_workflow_engine_starting",
        kafka=settings.kafka_bootstrap_servers,
        topics=[
            settings.kafka_topic_orders_confirmed,
            settings.kafka_topic_procurement_delivered,
            settings.kafka_topic_montage_completed,
        ],
        paperclip_url=settings.paperclip_api_url,
    )

    pool = await create_pool(settings.database_url)

    # Pre-resolve Paperclip agent IDs so the engine can assign issues
    await pc.resolve_agent_ids()

    consumer = WorkflowConsumer(pool)
    await consumer.start()

    loop = asyncio.get_running_loop()
    task = loop.create_task(consumer.run())

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
        await consumer.stop()
        await pool.close()
        log.info(
            "project_workflow_engine_stopped",
            received=consumer.total_received,
            processed=consumer.total_processed,
            errors=consumer.total_errors,
        )


if __name__ == "__main__":
    asyncio.run(main())
