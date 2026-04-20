"""ENTSO-E Transparency Platform HTTP client with circuit breaker."""
from __future__ import annotations

import httpx
import structlog

from circuit_breaker import CircuitBreaker
from config import settings

log = structlog.get_logger()

# documentType + processType per ENTSO-E feed
_QUERY_PARAMS: dict[str, dict[str, str]] = {
    "ActualTotalLoad": {"documentType": "A65", "processType": "A16"},
    "ImbalancePrices": {"documentType": "A85", "processType": "A46"},
    "AggregatedGenerationPerType": {"documentType": "A75", "processType": "A16"},
    "BalancingBorderCapacityLimitation": {"documentType": "A46", "processType": "A39"},
}


class EntsoEClient:
    def __init__(self) -> None:
        self._cb = CircuitBreaker(
            failure_threshold=settings.circuit_breaker_failure_threshold,
            recovery_timeout_sec=settings.circuit_breaker_recovery_timeout_sec,
        )
        # Stores last successful XML response per feed for fallback
        self._last_known: dict[str, bytes] = {}

    async def fetch(
        self,
        feed_name: str,
        period_start: str,
        period_end: str,
    ) -> bytes | None:
        """Fetch XML from ENTSO-E. Returns cached fallback when circuit is open."""
        if self._cb.is_open():
            log.warning(
                "circuit_open_fallback",
                feed=feed_name,
                cached=feed_name in self._last_known,
            )
            return self._last_known.get(feed_name)

        base_params = dict(_QUERY_PARAMS.get(feed_name, {}))
        base_params.update(
            {
                "securityToken": settings.entsoe_security_token,
                "in_Domain": settings.entsoe_area_eic,
                "out_Domain": settings.entsoe_area_eic,
                "periodStart": period_start,
                "periodEnd": period_end,
            }
        )

        try:
            async with httpx.AsyncClient(timeout=settings.entsoe_timeout_sec) as client:
                resp = await client.get(settings.entsoe_base_url, params=base_params)
                resp.raise_for_status()
                xml_bytes = resp.content
                self._last_known[feed_name] = xml_bytes
                self._cb.record_success()
                log.info("entsoe_fetched", feed=feed_name, bytes=len(xml_bytes))
                return xml_bytes
        except httpx.HTTPError as exc:
            self._cb.record_failure()
            log.error("entsoe_fetch_error", feed=feed_name, error=str(exc))
            return self._last_known.get(feed_name)
