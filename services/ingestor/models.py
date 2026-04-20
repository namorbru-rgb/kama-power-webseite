"""Pydantic models for inbound Kafka messages and DB records."""
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# Valid device types (matches devices.device_type in schema)
DEVICE_TYPES = frozenset(
    {"solar_inverter", "wind_turbine", "bess", "grid_meter", "smart_meter"}
)

# Valid directions (matches telemetry.direction in schema)
DIRECTIONS = frozenset(
    {"production", "consumption", "feed_in", "draw", "charge", "discharge"}
)


class TelemetryEvent(BaseModel):
    """Canonical event published by the edge agent (camelCase JSON from Go)."""

    siteId: UUID
    deviceId: UUID
    deviceType: str
    timestamp: datetime
    powerW: Optional[float] = None
    energyKwh: Optional[float] = None
    voltageV: Optional[float] = None
    currentA: Optional[float] = None
    freqHz: Optional[float] = None
    direction: str = ""
    socPct: Optional[float] = None
    extra: Optional[dict[str, Any]] = None

    @field_validator("deviceType")
    @classmethod
    def validate_device_type(cls, v: str) -> str:
        if v not in DEVICE_TYPES:
            raise ValueError(f"unknown deviceType: {v!r}")
        return v

    @field_validator("direction")
    @classmethod
    def validate_direction(cls, v: str) -> str:
        if v and v not in DIRECTIONS:
            raise ValueError(f"unknown direction: {v!r}")
        return v

    @field_validator("socPct")
    @classmethod
    def validate_soc(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (0.0 <= v <= 100.0):
            raise ValueError(f"socPct out of range: {v}")
        return v

    def to_db_row(self) -> dict[str, Any]:
        """Return a dict matching the telemetry hypertable column names."""
        return {
            "time": self.timestamp,
            "site_id": str(self.siteId),
            "device_id": str(self.deviceId),
            "device_type": self.deviceType,
            "power_w": self.powerW,
            "energy_kwh": self.energyKwh,
            "voltage_v": self.voltageV,
            "current_a": self.currentA,
            "frequency_hz": self.freqHz,
            "direction": self.direction or None,
            "soc_pct": self.socPct,
            "extra": self.extra,
        }
