"""Polling scheduler — drives ENTSO-E feeds on their respective intervals."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import structlog

from client import EntsoEClient
from config import settings
from influx_writer import InfluxWriter
from normalizer import normalize_xml
from producer import GridProducer

log = structlog.get_logger()

# Feed name → (poll_interval_minutes, lookback_minutes)
# Lookback is wider than the interval to handle API delivery lag.
_FEEDS: dict[str, tuple[int, int]] = {
    "ActualTotalLoad": (15, 90),
    "ImbalancePrices": (15, 90),
    "AggregatedGenerationPerType": (60, 180),
    "BalancingBorderCapacityLimitation": (60, 180),
}


def _fmt_period(dt: datetime) -> str:
    """ENTSO-E period format: YYYYMMDDHHmm (UTC)."""
    return dt.strftime("%Y%m%d%H%M")


class Poller:
    def __init__(
        self,
        client: EntsoEClient,
        producer: GridProducer,
        writer: InfluxWriter,
    ) -> None:
        self._client = client
        self._producer = producer
        self._writer = writer

    async def _poll_feed(self, feed_name: str, lookback_minutes: int) -> None:
        now = datetime.now(tz=timezone.utc)
        start = now - timedelta(minutes=lookback_minutes)
        xml_bytes = await self._client.fetch(
            feed_name,
            period_start=_fmt_period(start),
            period_end=_fmt_period(now),
        )
        if xml_bytes is None:
            log.warning("no_data_returned", feed=feed_name)
            return

        try:
            signals = normalize_xml(xml_bytes, feed_name)
        except Exception as exc:
            log.error("normalize_error", feed=feed_name, error=str(exc))
            return

        if not signals:
            log.info("no_signals_parsed", feed=feed_name)
            return

        await self._producer.publish([s.model_dump(mode="json") for s in signals])
        self._writer.write(signals)
        log.info("poll_complete", feed=feed_name, signals=len(signals))

    async def _run_periodic(
        self, feed_name: str, interval_min: int, lookback_min: int
    ) -> None:
        while True:
            try:
                await self._poll_feed(feed_name, lookback_min)
            except Exception as exc:
                log.error("poll_unhandled_error", feed=feed_name, error=str(exc))
            await asyncio.sleep(interval_min * 60)

    async def run(self) -> None:
        tasks = [
            asyncio.create_task(
                self._run_periodic(feed, interval, lookback),
                name=f"poll-{feed}",
            )
            for feed, (interval, lookback) in _FEEDS.items()
        ]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
