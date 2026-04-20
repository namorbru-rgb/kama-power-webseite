"""Unit tests for TelemetryEvent validation and DB row transformation."""
import pytest
from datetime import datetime, timezone
from uuid import uuid4

from models import TelemetryEvent


SITE_ID = str(uuid4())
DEVICE_ID = str(uuid4())
NOW = datetime.now(tz=timezone.utc).isoformat()


def _base(**overrides) -> dict:
    return {
        "siteId": SITE_ID,
        "deviceId": DEVICE_ID,
        "deviceType": "solar_inverter",
        "timestamp": NOW,
        "direction": "production",
        **overrides,
    }


def test_valid_minimal():
    evt = TelemetryEvent.model_validate(_base())
    assert evt.deviceType == "solar_inverter"
    assert evt.direction == "production"
    assert evt.powerW is None


def test_valid_full():
    data = _base(
        powerW=1500.0,
        energyKwh=12345.6,
        voltageV=230.1,
        currentA=6.5,
        freqHz=50.0,
        socPct=80.0,
        extra={"phase": "A"},
    )
    evt = TelemetryEvent.model_validate(data)
    row = evt.to_db_row()
    assert row["power_w"] == 1500.0
    assert row["soc_pct"] == 80.0
    assert row["extra"] == {"phase": "A"}
    assert row["site_id"] == SITE_ID
    assert row["device_id"] == DEVICE_ID


def test_to_db_row_column_names():
    evt = TelemetryEvent.model_validate(_base(powerW=100.0))
    row = evt.to_db_row()
    expected_keys = {
        "time", "site_id", "device_id", "device_type",
        "power_w", "energy_kwh", "voltage_v", "current_a",
        "frequency_hz", "direction", "soc_pct", "extra",
    }
    assert set(row.keys()) == expected_keys


def test_invalid_device_type():
    with pytest.raises(Exception):
        TelemetryEvent.model_validate(_base(deviceType="unknown_device"))


def test_invalid_direction():
    with pytest.raises(Exception):
        TelemetryEvent.model_validate(_base(direction="sideways"))


def test_soc_out_of_range_high():
    with pytest.raises(Exception):
        TelemetryEvent.model_validate(_base(deviceType="bess", socPct=101.0))


def test_soc_out_of_range_low():
    with pytest.raises(Exception):
        TelemetryEvent.model_validate(_base(deviceType="bess", socPct=-1.0))


def test_soc_boundary_values():
    evt_low = TelemetryEvent.model_validate(_base(deviceType="bess", socPct=0.0))
    evt_high = TelemetryEvent.model_validate(_base(deviceType="bess", socPct=100.0))
    assert evt_low.socPct == 0.0
    assert evt_high.socPct == 100.0


def test_empty_direction_becomes_none_in_db():
    evt = TelemetryEvent.model_validate(_base(direction=""))
    row = evt.to_db_row()
    assert row["direction"] is None


def test_all_device_types_accepted():
    for dtype in ("solar_inverter", "wind_turbine", "bess", "grid_meter", "smart_meter"):
        evt = TelemetryEvent.model_validate(_base(deviceType=dtype))
        assert evt.deviceType == dtype


def test_all_directions_accepted():
    for d in ("production", "consumption", "feed_in", "draw", "charge", "discharge"):
        evt = TelemetryEvent.model_validate(_base(direction=d))
        assert evt.direction == d


def test_grid_meter_event():
    data = _base(
        deviceType="grid_meter",
        direction="draw",
        powerW=800.0,
        voltageV=231.0,
        freqHz=49.98,
    )
    evt = TelemetryEvent.model_validate(data)
    row = evt.to_db_row()
    assert row["device_type"] == "grid_meter"
    assert row["direction"] == "draw"
    assert row["frequency_hz"] == 49.98
