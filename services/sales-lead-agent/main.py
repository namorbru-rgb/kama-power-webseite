"""KAMA Sales & Lead Agent — Leads generieren, Angebote erstellen, Aufträge erzeugen."""
import asyncio
import signal

import structlog

from config import settings
from consumer import SalesLeadAgent
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
        "sales_lead_agent_starting",
        kafka=settings.kafka_bootstrap_servers,
        topic_leads=settings.kafka_topic_leads_inbound,
        topic_reply=settings.kafka_topic_comm_reply,
        followup_days=[settings.followup_days_1, settings.followup_days_2],
        min_quote_chf=settings.min_quote_value_chf,
    )

    pool = await create_pool(settings.database_url)
    agent = SalesLeadAgent(pool)
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
            "sales_lead_agent_stopped",
            received=agent.total_received,
            processed=agent.total_processed,
            errors=agent.total_errors,
        )


if __name__ == "__main__":
    asyncio.run(main())
