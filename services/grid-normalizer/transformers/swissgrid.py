"""Swissgrid CSV → canonical GridSignal transformer.

Swissgrid publishes 15-minute interval operational grid data as semicolon-delimited
CSV files at https://www.swissgrid.ch/en/home/operation/grid-data/generation.html

Typical file structure (EN variant, UTF-8-BOM):
  Timestamp;Total Load [MW];Total Generation [MW];Renewables [MW];Nuclear [MW];...

Swiss variant uses German column headers:
  Zeitstempel;Verbrauch [MW];Einspeisung [MW];Erneuerbar [MW];Kernkraft [MW];...

Both variants are handled. Only columns listed in _COLUMN_MAP are extracted.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any

from models import DataQuality, GridSignal, SignalType

_SWISSGRID_EIC = "10YCH-SWISSGRIDC"

# (signal_type, unit) per column header
_COLUMN_MAP: dict[str, tuple[SignalType, str]] = {
    # German headers
    "Verbrauch [MW]": (SignalType.LOAD, "MW"),
    "Einspeisung [MW]": (SignalType.GENERATION, "MW"),
    "Produktion [MW]": (SignalType.GENERATION, "MW"),
    "Ausfuhr [MW]": (SignalType.CAPACITY, "MW"),
    "Einfuhr [MW]": (SignalType.CAPACITY, "MW"),
    "Regelzonenabweichung [MW]": (SignalType.IMBALANCE_PRICE, "MW"),
    # English headers
    "Total Load [MW]": (SignalType.LOAD, "MW"),
    "Total Generation [MW]": (SignalType.GENERATION, "MW"),
    "Export [MW]": (SignalType.CAPACITY, "MW"),
    "Import [MW]": (SignalType.CAPACITY, "MW"),
    "Control Zone Deviation [MW]": (SignalType.IMBALANCE_PRICE, "MW"),
}

# Column names that hold the timestamp (checked in order)
_TIMESTAMP_COLUMNS = ("Timestamp", "Zeitstempel", "Date", "Datum")

# Formats tried in order when parsing the timestamp cell
_TS_FORMATS = (
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
)


def _parse_timestamp(ts_str: str) -> datetime:
    ts_str = ts_str.strip()
    for fmt in _TS_FORMATS:
        try:
            return datetime.strptime(ts_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse Swissgrid timestamp: {ts_str!r}")


def _parse_value(raw: str) -> float | None:
    """Return float or None for blank / sentinel cells."""
    raw = raw.strip()
    if not raw or raw in ("-", "n/a", "N/A", "–"):
        return None
    # Swissgrid sometimes uses apostrophe as thousands separator: 8'012.5
    return float(raw.replace("'", "").replace(",", "."))


def transform_csv(
    csv_bytes: bytes,
    quality: DataQuality = DataQuality.MEASURED,
) -> list[GridSignal]:
    """Parse a Swissgrid CSV export and return canonical GridSignal objects.

    Args:
        csv_bytes: Raw CSV file content (UTF-8 with optional BOM).
        quality: DataQuality to assign to all produced signals.

    Returns:
        List of GridSignal objects; rows or columns that cannot be parsed are
        silently skipped.
    """
    text = csv_bytes.decode("utf-8-sig")  # strip BOM if present
    reader = csv.DictReader(io.StringIO(text), delimiter=";")

    signals: list[GridSignal] = []
    for row in reader:
        # Locate the timestamp cell
        ts_raw = next(
            (row[col] for col in _TIMESTAMP_COLUMNS if col in row and row[col]),
            None,
        )
        if ts_raw is None:
            continue
        try:
            timestamp = _parse_timestamp(ts_raw)
        except ValueError:
            continue

        for col, (signal_type, unit) in _COLUMN_MAP.items():
            if col not in row:
                continue
            value = _parse_value(row[col])
            if value is None:
                continue

            signals.append(
                GridSignal(
                    timestamp=timestamp,
                    dso_id=_SWISSGRID_EIC,
                    signal_type=signal_type,
                    value=value,
                    unit=unit,
                    location_eic=_SWISSGRID_EIC,
                    source="swissgrid",
                    quality=quality,
                    resolution="PT15M",
                    period_end=None,
                    meta={"column": col},
                )
            )

    return signals


def transform_row(
    row: dict[str, Any],
    quality: DataQuality = DataQuality.MEASURED,
) -> list[GridSignal]:
    """Transform a single pre-parsed CSV row dict (useful for streaming ingestion)."""
    ts_raw = next(
        (row[col] for col in _TIMESTAMP_COLUMNS if col in row and row[col]),
        None,
    )
    if ts_raw is None:
        raise ValueError("No timestamp column found in row")
    timestamp = _parse_timestamp(str(ts_raw))

    signals: list[GridSignal] = []
    for col, (signal_type, unit) in _COLUMN_MAP.items():
        if col not in row:
            continue
        value = _parse_value(str(row[col]))
        if value is None:
            continue
        signals.append(
            GridSignal(
                timestamp=timestamp,
                dso_id=_SWISSGRID_EIC,
                signal_type=signal_type,
                value=value,
                unit=unit,
                location_eic=_SWISSGRID_EIC,
                source="swissgrid",
                quality=quality,
                resolution="PT15M",
                meta={"column": col},
            )
        )
    return signals
