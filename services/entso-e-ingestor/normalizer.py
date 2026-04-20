"""XML → GridSignal normalization for ENTSO-E Transparency Platform responses."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel


# ENTSO-E resolution codes → timedelta
_RESOLUTION_MAP: dict[str, timedelta] = {
    "PT15M": timedelta(minutes=15),
    "PT30M": timedelta(minutes=30),
    "PT60M": timedelta(hours=1),
    "P1D": timedelta(days=1),
    "P1Y": timedelta(days=365),
}


class GridSignal(BaseModel):
    """Normalized grid signal ready for Kafka publication and InfluxDB storage."""

    measurement_type: str       # e.g. "ActualTotalLoad"
    period_start: datetime      # UTC start of this point's interval
    period_end: datetime        # UTC end of this point's interval
    resolution: str             # ISO 8601 duration, e.g. "PT15M"
    area_eic: str               # e.g. "10YCH-SWISSGRIDC"
    value: float
    unit: str                   # e.g. "MAW", "EUR_MWH"
    psr_type: str | None = None # power system resource type (generation only)
    extra: dict[str, Any] | None = None

    def to_influx_point(self) -> dict[str, Any]:
        """Return a dict suitable for building an influxdb-client Point."""
        tags: dict[str, str] = {
            "measurement_type": self.measurement_type,
            "area_eic": self.area_eic,
            "resolution": self.resolution,
            "unit": self.unit,
        }
        if self.psr_type:
            tags["psr_type"] = self.psr_type
        return {
            "measurement": "grid_switzerland",
            "tags": tags,
            "fields": {"value": self.value},
            "time": self.period_start,
        }


def _find_text(element: ET.Element, tag: str, ns_uri: str) -> str | None:
    child = element.find(f"{{{ns_uri}}}{tag}" if ns_uri else tag)
    if child is not None and child.text:
        return child.text.strip()
    # Fallback: try without namespace
    child = element.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return None


def _parse_utc(ts: str) -> datetime:
    """Parse ENTSO-E UTC timestamp (e.g. '2024-01-01T00:00Z') to aware datetime."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _resolution_to_delta(resolution: str) -> timedelta:
    delta = _RESOLUTION_MAP.get(resolution)
    if delta is None:
        raise ValueError(f"Unsupported resolution: {resolution!r}")
    return delta


def normalize_xml(xml_bytes: bytes, measurement_type: str) -> list[GridSignal]:
    """Parse an ENTSO-E XML response and return normalized GridSignal objects."""
    root = ET.fromstring(xml_bytes)

    # Detect namespace URI from root tag (e.g. "{urn:iec62325...}GL_MarketDocument")
    ns_uri = ""
    if root.tag.startswith("{"):
        ns_uri = root.tag[1 : root.tag.index("}")]

    def _tag(name: str) -> str:
        return f"{{{ns_uri}}}{name}" if ns_uri else name

    def find(el: ET.Element, name: str) -> str | None:
        return _find_text(el, name, ns_uri)

    signals: list[GridSignal] = []

    for ts in root.iter(_tag("TimeSeries")):
        # Determine area EIC — try various ENTSO-E field names
        area_eic = (
            find(ts, "inBiddingZone_Domain.mRID")
            or find(ts, "in_Domain.mRID")
            or find(ts, "outBiddingZone_Domain.mRID")
            or find(ts, "out_Domain.mRID")
            or ""
        )

        unit = (
            find(ts, "quantity_Measure_Unit.name")
            or find(ts, "price_Measure_Unit.name")
            or "MAW"
        )

        # PSR type present in generation mix responses
        psr_type: str | None = None
        mkt_ps = ts.find(_tag("MktPSRType"))
        if mkt_ps is not None:
            psr_type = find(mkt_ps, "psrType")

        for period in ts.iter(_tag("Period")):
            interval = period.find(_tag("timeInterval"))
            if interval is None:
                continue
            start_str = find(interval, "start")
            end_str = find(interval, "end")
            if not start_str or not end_str:
                continue

            interval_start = _parse_utc(start_str)
            resolution = find(period, "resolution") or "PT60M"
            delta = _resolution_to_delta(resolution)

            for point in period.iter(_tag("Point")):
                pos_str = find(point, "position")
                qty_str = (
                    find(point, "quantity")
                    or find(point, "imbalance_Price.amount")
                )
                if not pos_str or not qty_str:
                    continue
                try:
                    position = int(pos_str)
                    value = float(qty_str)
                except ValueError:
                    continue

                point_start = interval_start + delta * (position - 1)
                point_end = point_start + delta

                signals.append(
                    GridSignal(
                        measurement_type=measurement_type,
                        period_start=point_start,
                        period_end=point_end,
                        resolution=resolution,
                        area_eic=area_eic,
                        value=value,
                        unit=unit,
                        psr_type=psr_type,
                    )
                )

    return signals
