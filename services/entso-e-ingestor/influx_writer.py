"""InfluxDB 2.x writer — stores normalized GridSignals in 'grid_switzerland'."""
from __future__ import annotations

import structlog
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

from config import settings
from normalizer import GridSignal

log = structlog.get_logger()


class InfluxWriter:
    def __init__(self) -> None:
        self._client = InfluxDBClient(
            url=settings.influx_url,
            token=settings.influx_token,
            org=settings.influx_org,
        )
        self._write_api = self._client.write_api(write_options=SYNCHRONOUS)

    def write(self, signals: list[GridSignal]) -> None:
        if not signals:
            return
        points: list[Point] = []
        for sig in signals:
            p_data = sig.to_influx_point()
            p = Point(p_data["measurement"])
            for k, v in p_data["tags"].items():
                p = p.tag(k, v)
            for k, v in p_data["fields"].items():
                p = p.field(k, v)
            p = p.time(p_data["time"], WritePrecision.SECONDS)
            points.append(p)
        try:
            self._write_api.write(
                bucket=settings.influx_bucket,
                org=settings.influx_org,
                record=points,
            )
            log.info("influx_written", bucket=settings.influx_bucket, count=len(points))
        except Exception as exc:
            log.error("influx_write_error", error=str(exc), count=len(points))
            raise

    def close(self) -> None:
        self._client.close()
