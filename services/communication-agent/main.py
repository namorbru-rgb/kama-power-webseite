"""KAMA Communication Agent — Kafka + Email + Telegram + SOP generation."""
import asyncio
import signal

import structlog

from config import settings
from consumer import CommunicationAgent
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
        "communication_agent_starting",
        kafka=settings.kafka_bootstrap_servers,
        imap_host=settings.imap_host,
        telegram_enabled=bool(settings.telegram_bot_token),
    )

    pool = await create_pool(settings.database_url)
    agent = CommunicationAgent(pool)
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
            "communication_agent_stopped",
            received=agent.total_received,
            processed=agent.total_processed,
            errors=agent.total_errors,
        )


if __name__ == "__main__":
    asyncio.run(main())
