"""
Report generator entry point.
Runs the weekly report immediately (one-shot) or on a cron schedule.

Usage:
  python main.py             # one-shot
  python main.py --schedule  # run on cron (blocks)
"""

import asyncio
import sys

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import settings
from report_generator import run_report

log = structlog.get_logger()


def main() -> None:
    scheduled = "--schedule" in sys.argv

    if not scheduled:
        asyncio.run(run_report())
        return

    scheduler = AsyncIOScheduler(timezone="Europe/Zurich")
    # Parse the cron expression from config (e.g. "0 7 * * 1" = Mon 07:00)
    parts = settings.report_schedule.split()
    if len(parts) != 5:
        log.error("Invalid cron schedule", schedule=settings.report_schedule)
        sys.exit(1)

    minute, hour, day, month, day_of_week = parts
    trigger = CronTrigger(
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=day_of_week,
        timezone="Europe/Zurich",
    )
    scheduler.add_job(run_report, trigger, misfire_grace_time=300)
    scheduler.start()
    log.info(
        "Report scheduler started",
        schedule=settings.report_schedule,
        recipients=settings.report_recipients,
    )

    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        log.info("Scheduler stopped")


if __name__ == "__main__":
    main()
