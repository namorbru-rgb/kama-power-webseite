from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


# ── Site ─────────────────────────────────────────────────────────────────────

class SiteBase(BaseModel):
    name: str
    address: Optional[str] = None
    timezone: str = "Europe/Zurich"
    lat: Optional[float] = None
    lon: Optional[float] = None


class SiteCreate(SiteBase):
    pass


class Site(SiteBase):
    id: UUID
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Device ────────────────────────────────────────────────────────────────────

class DeviceBase(BaseModel):
    name: str
    device_type: str
    protocol: str
    config: dict = {}
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None


class DeviceCreate(DeviceBase):
    site_id: UUID


class Device(DeviceBase):
    id: UUID
    site_id: UUID
    active: bool
    last_seen: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Telemetry reading ─────────────────────────────────────────────────────────

class TelemetryReading(BaseModel):
    time: datetime
    site_id: UUID
    device_id: UUID
    device_type: str
    power_w: Optional[float] = None
    energy_kwh: Optional[float] = None
    voltage_v: Optional[float] = None
    current_a: Optional[float] = None
    frequency_hz: Optional[float] = None
    direction: Optional[str] = None
    soc_pct: Optional[float] = None
    extra: Optional[dict] = None


# ── API response shapes ───────────────────────────────────────────────────────

class CurrentReading(BaseModel):
    """Latest live snapshot for a site."""
    site_id: UUID
    recorded_at: datetime
    production_w: float = 0.0    # solar + wind total
    consumption_w: float = 0.0
    feed_in_w: float = 0.0       # positive = exporting
    draw_w: float = 0.0          # positive = importing from grid
    bess_power_w: float = 0.0    # positive = charging
    bess_soc_pct: Optional[float] = None
    self_sufficiency_pct: float = 0.0


class DailySummary(BaseModel):
    site_id: UUID
    date: str                     # YYYY-MM-DD
    production_kwh: float = 0.0
    consumption_kwh: float = 0.0
    feed_in_kwh: float = 0.0
    draw_kwh: float = 0.0
    self_sufficiency_pct: float = 0.0
    co2_avoided_kg: float = 0.0   # using Swiss grid emission factor
    feed_in_revenue_chf: Optional[float] = None


class TrendPoint(BaseModel):
    bucket: datetime
    production_kwh: float = 0.0
    consumption_kwh: float = 0.0
    feed_in_kwh: float = 0.0
    draw_kwh: float = 0.0


class TrendResponse(BaseModel):
    site_id: UUID
    resolution: str               # "15m" | "hourly" | "daily"
    points: list[TrendPoint]
