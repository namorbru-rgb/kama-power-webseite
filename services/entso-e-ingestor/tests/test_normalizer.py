"""Unit tests for ENTSO-E XML normalization layer."""
from datetime import datetime, timedelta, timezone

import pytest

from normalizer import GridSignal, _parse_utc, _resolution_to_delta, normalize_xml


# ── Fixture XML documents ────────────────────────────────────────────────────

_ACTUAL_TOTAL_LOAD_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<GL_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0">
  <mRID>doc-001</mRID>
  <type>A65</type>
  <TimeSeries>
    <mRID>ts-001</mRID>
    <inBiddingZone_Domain.mRID>10YCH-SWISSGRIDC</inBiddingZone_Domain.mRID>
    <quantity_Measure_Unit.name>MAW</quantity_Measure_Unit.name>
    <Period>
      <timeInterval>
        <start>2024-01-15T10:00Z</start>
        <end>2024-01-15T11:00Z</end>
      </timeInterval>
      <resolution>PT15M</resolution>
      <Point><position>1</position><quantity>8012</quantity></Point>
      <Point><position>2</position><quantity>8150</quantity></Point>
      <Point><position>3</position><quantity>8200</quantity></Point>
      <Point><position>4</position><quantity>8050</quantity></Point>
    </Period>
  </TimeSeries>
</GL_MarketDocument>
"""

_GENERATION_MIX_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<GL_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0">
  <TimeSeries>
    <inBiddingZone_Domain.mRID>10YCH-SWISSGRIDC</inBiddingZone_Domain.mRID>
    <quantity_Measure_Unit.name>MAW</quantity_Measure_Unit.name>
    <MktPSRType>
      <psrType>B16</psrType>
    </MktPSRType>
    <Period>
      <timeInterval>
        <start>2024-01-15T10:00Z</start>
        <end>2024-01-15T11:00Z</end>
      </timeInterval>
      <resolution>PT60M</resolution>
      <Point><position>1</position><quantity>500</quantity></Point>
    </Period>
  </TimeSeries>
</GL_MarketDocument>
"""

_MULTI_TIMESERIES_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<GL_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0">
  <TimeSeries>
    <inBiddingZone_Domain.mRID>10YCH-SWISSGRIDC</inBiddingZone_Domain.mRID>
    <quantity_Measure_Unit.name>MAW</quantity_Measure_Unit.name>
    <MktPSRType><psrType>B01</psrType></MktPSRType>
    <Period>
      <timeInterval><start>2024-01-15T00:00Z</start><end>2024-01-15T01:00Z</end></timeInterval>
      <resolution>PT60M</resolution>
      <Point><position>1</position><quantity>100</quantity></Point>
    </Period>
  </TimeSeries>
  <TimeSeries>
    <inBiddingZone_Domain.mRID>10YCH-SWISSGRIDC</inBiddingZone_Domain.mRID>
    <quantity_Measure_Unit.name>MAW</quantity_Measure_Unit.name>
    <MktPSRType><psrType>B16</psrType></MktPSRType>
    <Period>
      <timeInterval><start>2024-01-15T00:00Z</start><end>2024-01-15T01:00Z</end></timeInterval>
      <resolution>PT60M</resolution>
      <Point><position>1</position><quantity>450</quantity></Point>
    </Period>
  </TimeSeries>
</GL_MarketDocument>
"""

_NO_DATA_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<GL_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0">
</GL_MarketDocument>
"""

_DAILY_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<GL_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0">
  <TimeSeries>
    <inBiddingZone_Domain.mRID>10YCH-SWISSGRIDC</inBiddingZone_Domain.mRID>
    <quantity_Measure_Unit.name>MAW</quantity_Measure_Unit.name>
    <Period>
      <timeInterval>
        <start>2024-01-15T00:00Z</start>
        <end>2024-01-17T00:00Z</end>
      </timeInterval>
      <resolution>P1D</resolution>
      <Point><position>1</position><quantity>7500</quantity></Point>
      <Point><position>2</position><quantity>7600</quantity></Point>
    </Period>
  </TimeSeries>
</GL_MarketDocument>
"""


# ── normalize_xml tests ───────────────────────────────────────────────────────

def test_normalize_actual_total_load_count():
    signals = normalize_xml(_ACTUAL_TOTAL_LOAD_XML, "ActualTotalLoad")
    assert len(signals) == 4


def test_normalize_measurement_type():
    signals = normalize_xml(_ACTUAL_TOTAL_LOAD_XML, "ActualTotalLoad")
    assert all(s.measurement_type == "ActualTotalLoad" for s in signals)


def test_normalize_area_eic():
    signals = normalize_xml(_ACTUAL_TOTAL_LOAD_XML, "ActualTotalLoad")
    assert all(s.area_eic == "10YCH-SWISSGRIDC" for s in signals)


def test_normalize_values():
    signals = normalize_xml(_ACTUAL_TOTAL_LOAD_XML, "ActualTotalLoad")
    assert signals[0].value == 8012.0
    assert signals[1].value == 8150.0
    assert signals[2].value == 8200.0
    assert signals[3].value == 8050.0


def test_normalize_period_start_15m():
    signals = normalize_xml(_ACTUAL_TOTAL_LOAD_XML, "ActualTotalLoad")
    base = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
    assert signals[0].period_start == base
    assert signals[1].period_start == base + timedelta(minutes=15)
    assert signals[2].period_start == base + timedelta(minutes=30)
    assert signals[3].period_start == base + timedelta(minutes=45)


def test_normalize_period_end_15m():
    signals = normalize_xml(_ACTUAL_TOTAL_LOAD_XML, "ActualTotalLoad")
    base = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
    assert signals[0].period_end == base + timedelta(minutes=15)
    assert signals[3].period_end == base + timedelta(hours=1)


def test_normalize_resolution():
    signals = normalize_xml(_ACTUAL_TOTAL_LOAD_XML, "ActualTotalLoad")
    assert all(s.resolution == "PT15M" for s in signals)


def test_normalize_unit():
    signals = normalize_xml(_ACTUAL_TOTAL_LOAD_XML, "ActualTotalLoad")
    assert all(s.unit == "MAW" for s in signals)


def test_normalize_no_psr_type_when_absent():
    signals = normalize_xml(_ACTUAL_TOTAL_LOAD_XML, "ActualTotalLoad")
    assert all(s.psr_type is None for s in signals)


def test_normalize_generation_psr_type():
    signals = normalize_xml(_GENERATION_MIX_XML, "AggregatedGenerationPerType")
    assert len(signals) == 1
    assert signals[0].psr_type == "B16"


def test_normalize_generation_resolution_hourly():
    signals = normalize_xml(_GENERATION_MIX_XML, "AggregatedGenerationPerType")
    assert signals[0].resolution == "PT60M"


def test_normalize_multi_timeseries():
    signals = normalize_xml(_MULTI_TIMESERIES_XML, "AggregatedGenerationPerType")
    assert len(signals) == 2
    psr_types = {s.psr_type for s in signals}
    assert psr_types == {"B01", "B16"}


def test_normalize_daily_resolution():
    signals = normalize_xml(_DAILY_XML, "ActualTotalLoad")
    assert len(signals) == 2
    assert signals[0].resolution == "P1D"
    assert signals[1].period_start == datetime(2024, 1, 16, 0, 0, tzinfo=timezone.utc)


def test_normalize_no_data_returns_empty():
    signals = normalize_xml(_NO_DATA_XML, "ActualTotalLoad")
    assert signals == []


# ── to_influx_point tests ─────────────────────────────────────────────────────

def test_to_influx_point_measurement_name():
    signals = normalize_xml(_ACTUAL_TOTAL_LOAD_XML, "ActualTotalLoad")
    point = signals[0].to_influx_point()
    assert point["measurement"] == "grid_switzerland"


def test_to_influx_point_tags():
    signals = normalize_xml(_ACTUAL_TOTAL_LOAD_XML, "ActualTotalLoad")
    tags = signals[0].to_influx_point()["tags"]
    assert tags["measurement_type"] == "ActualTotalLoad"
    assert tags["area_eic"] == "10YCH-SWISSGRIDC"
    assert tags["resolution"] == "PT15M"
    assert tags["unit"] == "MAW"


def test_to_influx_point_field_value():
    signals = normalize_xml(_ACTUAL_TOTAL_LOAD_XML, "ActualTotalLoad")
    assert signals[0].to_influx_point()["fields"]["value"] == 8012.0


def test_to_influx_point_time():
    signals = normalize_xml(_ACTUAL_TOTAL_LOAD_XML, "ActualTotalLoad")
    assert signals[0].to_influx_point()["time"] == datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)


def test_to_influx_point_psr_type_tag_included():
    signals = normalize_xml(_GENERATION_MIX_XML, "AggregatedGenerationPerType")
    tags = signals[0].to_influx_point()["tags"]
    assert tags.get("psr_type") == "B16"


def test_to_influx_point_no_psr_type_tag_when_absent():
    signals = normalize_xml(_ACTUAL_TOTAL_LOAD_XML, "ActualTotalLoad")
    tags = signals[0].to_influx_point()["tags"]
    assert "psr_type" not in tags


# ── GridSignal model tests ────────────────────────────────────────────────────

def test_grid_signal_defaults():
    sig = GridSignal(
        measurement_type="ActualTotalLoad",
        period_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        period_end=datetime(2024, 1, 1, 0, 15, tzinfo=timezone.utc),
        resolution="PT15M",
        area_eic="10YCH-SWISSGRIDC",
        value=8000.0,
        unit="MAW",
    )
    assert sig.psr_type is None
    assert sig.extra is None


def test_grid_signal_model_dump_json_serializable():
    signals = normalize_xml(_ACTUAL_TOTAL_LOAD_XML, "ActualTotalLoad")
    dump = signals[0].model_dump(mode="json")
    assert isinstance(dump["period_start"], str)
    assert dump["value"] == 8012.0


# ── Helper function tests ─────────────────────────────────────────────────────

def test_parse_utc_z_suffix():
    dt = _parse_utc("2024-01-15T10:00Z")
    assert dt.tzinfo is not None
    assert dt == datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)


def test_parse_utc_offset_suffix():
    dt = _parse_utc("2024-01-15T10:00+00:00")
    assert dt == datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)


def test_resolution_to_delta_15m():
    assert _resolution_to_delta("PT15M") == timedelta(minutes=15)


def test_resolution_to_delta_30m():
    assert _resolution_to_delta("PT30M") == timedelta(minutes=30)


def test_resolution_to_delta_hourly():
    assert _resolution_to_delta("PT60M") == timedelta(hours=1)


def test_resolution_to_delta_daily():
    assert _resolution_to_delta("P1D") == timedelta(days=1)


def test_resolution_unsupported_raises():
    with pytest.raises(ValueError, match="Unsupported resolution"):
        _resolution_to_delta("PT5M")
