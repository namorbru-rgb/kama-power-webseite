"""Unit tests for ENTSO-E and Swissgrid transformers."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import DataQuality, GridSignal, SignalType
from transformers import entso_e, swissgrid


# ── ENTSO-E transformer ───────────────────────────────────────────────────────

_ENTSO_E_LOAD = {
    "measurement_type": "ActualTotalLoad",
    "period_start": "2024-01-15T10:00:00+00:00",
    "period_end": "2024-01-15T10:15:00+00:00",
    "resolution": "PT15M",
    "area_eic": "10YCH-SWISSGRIDC",
    "value": 8012.0,
    "unit": "MAW",
    "psr_type": None,
    "extra": None,
}

_ENTSO_E_IMBALANCE = {
    "measurement_type": "ImbalancePrices",
    "period_start": "2024-01-15T10:00:00+00:00",
    "period_end": "2024-01-15T10:15:00+00:00",
    "resolution": "PT15M",
    "area_eic": "10YCH-SWISSGRIDC",
    "value": 142.50,
    "unit": "EUR_MWH",
    "psr_type": None,
    "extra": None,
}

_ENTSO_E_GENERATION = {
    "measurement_type": "AggregatedGenerationPerType",
    "period_start": "2024-01-15T10:00:00+00:00",
    "period_end": "2024-01-15T11:00:00+00:00",
    "resolution": "PT60M",
    "area_eic": "10YCH-SWISSGRIDC",
    "value": 500.0,
    "unit": "MAW",
    "psr_type": "B16",
    "extra": None,
}


def test_entso_e_load_signal_type():
    sig = entso_e.transform(_ENTSO_E_LOAD)
    assert sig.signal_type == SignalType.LOAD


def test_entso_e_load_source():
    sig = entso_e.transform(_ENTSO_E_LOAD)
    assert sig.source == "entso-e"


def test_entso_e_load_unit_normalised():
    sig = entso_e.transform(_ENTSO_E_LOAD)
    assert sig.unit == "MW"


def test_entso_e_load_quality():
    sig = entso_e.transform(_ENTSO_E_LOAD)
    assert sig.quality == DataQuality.MEASURED


def test_entso_e_load_timestamp():
    sig = entso_e.transform(_ENTSO_E_LOAD)
    assert sig.timestamp == datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)


def test_entso_e_load_location_eic():
    sig = entso_e.transform(_ENTSO_E_LOAD)
    assert sig.location_eic == "10YCH-SWISSGRIDC"


def test_entso_e_load_value():
    sig = entso_e.transform(_ENTSO_E_LOAD)
    assert sig.value == 8012.0


def test_entso_e_load_resolution():
    sig = entso_e.transform(_ENTSO_E_LOAD)
    assert sig.resolution == "PT15M"


def test_entso_e_load_period_end():
    sig = entso_e.transform(_ENTSO_E_LOAD)
    assert sig.period_end == datetime(2024, 1, 15, 10, 15, tzinfo=timezone.utc)


def test_entso_e_imbalance_signal_type():
    sig = entso_e.transform(_ENTSO_E_IMBALANCE)
    assert sig.signal_type == SignalType.IMBALANCE_PRICE


def test_entso_e_imbalance_unit_normalised():
    sig = entso_e.transform(_ENTSO_E_IMBALANCE)
    assert sig.unit == "EUR/MWh"


def test_entso_e_generation_psr_type_in_meta():
    sig = entso_e.transform(_ENTSO_E_GENERATION)
    assert sig.signal_type == SignalType.GENERATION
    assert sig.meta is not None
    assert sig.meta.get("psr_type") == "B16"


def test_entso_e_no_psr_type_meta_absent():
    sig = entso_e.transform(_ENTSO_E_LOAD)
    assert sig.meta is None or "psr_type" not in sig.meta


def test_entso_e_missing_required_field_raises():
    bad = dict(_ENTSO_E_LOAD)
    del bad["measurement_type"]
    with pytest.raises(KeyError):
        entso_e.transform(bad)


def test_entso_e_transform_batch_skips_bad():
    good = _ENTSO_E_LOAD
    bad = {"bad": "data"}
    results = entso_e.transform_batch([good, bad, good])
    assert len(results) == 2


def test_entso_e_to_kafka_dict_serializable():
    import json
    sig = entso_e.transform(_ENTSO_E_LOAD)
    d = sig.to_kafka_dict()
    # Must be JSON-serializable (datetime already converted to str by model_dump mode=json)
    json.dumps(d)
    assert d["signal_type"] == "LOAD"
    assert d["quality"] == "measured"


# ── Swissgrid transformer ─────────────────────────────────────────────────────

_SWISSGRID_CSV_DE = (
    "Zeitstempel;Verbrauch [MW];Einspeisung [MW];Ausfuhr [MW];Einfuhr [MW]\n"
    "2024-01-15T10:00;7500.0;8000.0;300.0;200.0\n"
    "2024-01-15T10:15;7600.0;8100.0;310.0;190.0\n"
).encode()

_SWISSGRID_CSV_EN = (
    "Timestamp;Total Load [MW];Total Generation [MW];Export [MW];Import [MW]\n"
    "2024-01-15T10:00;7500.0;8000.0;300.0;200.0\n"
).encode()

_SWISSGRID_CSV_APOSTROPHE = (
    "Zeitstempel;Verbrauch [MW]\n"
    "2024-01-15T10:00;8'012.5\n"
).encode()

_SWISSGRID_CSV_DOT_DATE = (
    "Zeitstempel;Verbrauch [MW]\n"
    "15.01.2024 10:00;7500.0\n"
).encode()

_SWISSGRID_CSV_MISSING_VALUE = (
    "Zeitstempel;Verbrauch [MW];Einspeisung [MW]\n"
    "2024-01-15T10:00;-;8000.0\n"
).encode()


def test_swissgrid_de_signal_count():
    # 2 rows × 4 data columns = 8 signals
    sigs = swissgrid.transform_csv(_SWISSGRID_CSV_DE)
    assert len(sigs) == 8


def test_swissgrid_de_load_signal_type():
    sigs = swissgrid.transform_csv(_SWISSGRID_CSV_DE)
    load_sigs = [s for s in sigs if s.signal_type == SignalType.LOAD]
    assert len(load_sigs) == 2


def test_swissgrid_de_source():
    sigs = swissgrid.transform_csv(_SWISSGRID_CSV_DE)
    assert all(s.source == "swissgrid" for s in sigs)


def test_swissgrid_de_location_eic():
    sigs = swissgrid.transform_csv(_SWISSGRID_CSV_DE)
    assert all(s.location_eic == "10YCH-SWISSGRIDC" for s in sigs)


def test_swissgrid_de_quality_default():
    sigs = swissgrid.transform_csv(_SWISSGRID_CSV_DE)
    assert all(s.quality == DataQuality.MEASURED for s in sigs)


def test_swissgrid_de_resolution():
    sigs = swissgrid.transform_csv(_SWISSGRID_CSV_DE)
    assert all(s.resolution == "PT15M" for s in sigs)


def test_swissgrid_de_timestamp_first_row():
    sigs = swissgrid.transform_csv(_SWISSGRID_CSV_DE)
    first_ts = {s.timestamp for s in sigs if s.signal_type == SignalType.LOAD}
    assert datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc) in first_ts


def test_swissgrid_en_signal_count():
    sigs = swissgrid.transform_csv(_SWISSGRID_CSV_EN)
    assert len(sigs) == 4


def test_swissgrid_apostrophe_thousands_separator():
    sigs = swissgrid.transform_csv(_SWISSGRID_CSV_APOSTROPHE)
    assert len(sigs) == 1
    assert sigs[0].value == 8012.5


def test_swissgrid_dot_date_format():
    sigs = swissgrid.transform_csv(_SWISSGRID_CSV_DOT_DATE)
    assert len(sigs) == 1
    assert sigs[0].timestamp == datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)


def test_swissgrid_sentinel_dash_skipped():
    sigs = swissgrid.transform_csv(_SWISSGRID_CSV_MISSING_VALUE)
    # Verbrauch is "-" → skipped, Einspeisung is valid → 1 signal
    assert len(sigs) == 1
    assert sigs[0].signal_type == SignalType.GENERATION


def test_swissgrid_forecast_quality():
    sigs = swissgrid.transform_csv(_SWISSGRID_CSV_EN, quality=DataQuality.FORECAST)
    assert all(s.quality == DataQuality.FORECAST for s in sigs)


def test_swissgrid_meta_contains_column():
    sigs = swissgrid.transform_csv(_SWISSGRID_CSV_DE)
    for s in sigs:
        assert s.meta is not None
        assert "column" in s.meta


# ── GridSignal model ──────────────────────────────────────────────────────────

def test_grid_signal_to_db_row_keys():
    sig = entso_e.transform(_ENTSO_E_LOAD)
    row = sig.to_db_row()
    expected_keys = {
        "timestamp", "dso_id", "signal_type", "value", "unit",
        "location_eic", "source", "quality", "resolution", "period_end", "meta",
    }
    assert set(row.keys()) == expected_keys


def test_grid_signal_to_db_row_signal_type_is_string():
    sig = entso_e.transform(_ENTSO_E_LOAD)
    row = sig.to_db_row()
    assert isinstance(row["signal_type"], str)
    assert row["signal_type"] == "LOAD"
