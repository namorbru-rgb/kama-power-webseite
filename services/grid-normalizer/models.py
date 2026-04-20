"""Canonical GridSignal data model — DSO-agnostic contract for the optimization engine."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class SignalType(str, Enum):
    IMBALANCE_PRICE = "IMBALANCE_PRICE"
    TARIFF = "TARIFF"
    LOAD = "LOAD"
    CAPACITY = "CAPACITY"
    CONGESTION = "CONGESTION"
    FREQUENCY = "FREQUENCY"
    GENERATION = "GENERATION"


class DataQuality(str, Enum):
    MEASURED = "measured"
    ESTIMATED = "estimated"
    FORECAST = "forecast"


class GridSignal(BaseModel):
    """
    Normalized, source-agnostic grid signal consumed by the KAMA optimization engine.

    All timestamps are UTC-aware. All values are in SI-adjacent units as declared in `unit`.
    Schema is registered as energy.kama.grid.GridSignal in the Confluent Schema Registry.
    """

    timestamp: datetime           # UTC start of measurement interval
    dso_id: str                   # EIC code or internal DSO identifier
    signal_type: SignalType       # semantic signal category
    value: float                  # numeric value in `unit`
    unit: str                     # e.g. MW, EUR/MWh, CHF/kWh, Hz
    location_eic: str             # ENTSO-E bidding zone or grid node EIC
    source: str                   # entso-e | swissgrid | ewz | bkw | elcom
    quality: DataQuality          # measured | estimated | forecast
    resolution: str | None = None # ISO 8601 duration, e.g. PT15M
    period_end: datetime | None = None
    meta: dict[str, Any] | None = None

    def to_kafka_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-safe dict for Kafka publication."""
        d = self.model_dump(mode="json")
        # Avro enum values must be plain strings
        d["signal_type"] = self.signal_type.value
        d["quality"] = self.quality.value
        return d

    def to_db_row(self) -> dict[str, Any]:
        """Return a dict matching the grid_signals TimescaleDB hypertable columns."""
        return {
            "timestamp": self.timestamp,
            "dso_id": self.dso_id,
            "signal_type": self.signal_type.value,
            "value": self.value,
            "unit": self.unit,
            "location_eic": self.location_eic,
            "source": self.source,
            "quality": self.quality.value,
            "resolution": self.resolution,
            "period_end": self.period_end,
            "meta": self.meta,
        }
