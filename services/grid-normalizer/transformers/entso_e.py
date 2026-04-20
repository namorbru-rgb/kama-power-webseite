"""ENTSO-E → canonical GridSignal transformer.

Consumes JSON messages from the `grid.entso-e.raw` Kafka topic, which carry the
entso-e-ingestor's internal GridSignal schema, and maps them to the DSO-agnostic
canonical model.

ENTSO-E raw message fields (from services/entso-e-ingestor/normalizer.py):
  measurement_type, period_start, period_end, resolution, area_eic, value, unit,
  psr_type (optional), extra (optional)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from models import DataQuality, GridSignal, SignalType

# ENTSO-E measurement_type → canonical SignalType
_MEASUREMENT_TO_SIGNAL: dict[str, SignalType] = {
    "ActualTotalLoad": SignalType.LOAD,
    "ImbalancePrices": SignalType.IMBALANCE_PRICE,
    "AggregatedGenerationPerType": SignalType.GENERATION,
    "BalancingBorderCapacityLimitation": SignalType.CAPACITY,
    "DayAheadPrices": SignalType.TARIFF,
    "CrossBorderFlows": SignalType.CAPACITY,
    "ScheduledExchanges": SignalType.CAPACITY,
    "SystemFrequency": SignalType.FREQUENCY,
}

# ENTSO-E unit codes → human-readable unit strings
_UNIT_NORMALISE: dict[str, str] = {
    "MAW": "MW",
    "KWH": "kWh",
    "MWH": "MWh",
    "EUR_MWH": "EUR/MWh",
    "CHF_MWH": "CHF/MWh",
    "HZ": "Hz",
}


def _parse_dt(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def transform(raw: dict[str, Any]) -> GridSignal:
    """Map a single ENTSO-E raw Kafka message to a canonical GridSignal.

    Raises KeyError / ValueError when required fields are absent or malformed.
    """
    measurement_type: str = raw["measurement_type"]
    signal_type = _MEASUREMENT_TO_SIGNAL.get(measurement_type, SignalType.LOAD)

    raw_unit = raw.get("unit", "MAW")
    unit = _UNIT_NORMALISE.get(raw_unit, raw_unit)

    timestamp = _parse_dt(raw["period_start"])
    period_end_raw = raw.get("period_end")
    period_end = _parse_dt(period_end_raw) if period_end_raw else None

    area_eic: str = raw.get("area_eic", "")

    meta: dict[str, str] = {}
    if raw.get("psr_type"):
        meta["psr_type"] = raw["psr_type"]
    if measurement_type:
        meta["measurement_type"] = measurement_type

    return GridSignal(
        timestamp=timestamp,
        dso_id=area_eic,
        signal_type=signal_type,
        value=float(raw["value"]),
        unit=unit,
        location_eic=area_eic,
        source="entso-e",
        quality=DataQuality.MEASURED,
        resolution=raw.get("resolution"),
        period_end=period_end,
        meta=meta or None,
    )


def transform_batch(messages: list[dict[str, Any]]) -> list[GridSignal]:
    """Transform a list of raw ENTSO-E messages; skip unparseable entries."""
    import structlog
    log = structlog.get_logger()
    out: list[GridSignal] = []
    for msg in messages:
        try:
            out.append(transform(msg))
        except (KeyError, ValueError, TypeError) as exc:
            log.warning("entso_e_transform_skipped", error=str(exc), msg=msg)
    return out
