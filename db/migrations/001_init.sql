-- KAMA Energy Platform — TimescaleDB Schema
-- Migration 001: Initial schema

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ─────────────────────────────────────────────────────────────────
-- Reference tables
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE sites (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    address     TEXT,
    timezone    TEXT NOT NULL DEFAULT 'Europe/Zurich',
    lat         DOUBLE PRECISION,
    lon         DOUBLE PRECISION,
    active      BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE devices (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id     UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    -- Types: solar_inverter, wind_turbine, bess, grid_meter, smart_meter
    device_type TEXT NOT NULL,
    -- Protocols: mqtt, modbus_tcp, modbus_rtu, http_push, solarman_v5
    protocol    TEXT NOT NULL,
    -- Device-specific connection params (host, port, unit_id, topic, etc.)
    config      JSONB NOT NULL DEFAULT '{}',
    manufacturer TEXT,
    model        TEXT,
    serial_number TEXT,
    firmware_version TEXT,
    active      BOOLEAN NOT NULL DEFAULT true,
    last_seen   TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_devices_site_id ON devices(site_id);
CREATE INDEX idx_devices_device_type ON devices(device_type);

-- ─────────────────────────────────────────────────────────────────
-- Telemetry hypertable (raw 1-min readings)
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE telemetry (
    time        TIMESTAMPTZ     NOT NULL,
    site_id     UUID            NOT NULL REFERENCES sites(id),
    device_id   UUID            NOT NULL REFERENCES devices(id),
    device_type TEXT            NOT NULL,
    -- Power measurements
    power_w     DOUBLE PRECISION,        -- instantaneous power (W), positive = production/feed-in
    energy_kwh  DOUBLE PRECISION,        -- cumulative energy counter (kWh)
    -- Electrical measurements
    voltage_v   DOUBLE PRECISION,
    current_a   DOUBLE PRECISION,
    frequency_hz DOUBLE PRECISION,
    -- Direction: production | consumption | feed_in | draw | charge | discharge
    direction   TEXT,
    -- State of charge (BESS only, 0-100)
    soc_pct     DOUBLE PRECISION,
    -- Catch-all for device-specific fields
    extra       JSONB
);

SELECT create_hypertable('telemetry', 'time', chunk_time_interval => INTERVAL '1 day');

CREATE INDEX idx_telemetry_site_time ON telemetry(site_id, time DESC);
CREATE INDEX idx_telemetry_device_time ON telemetry(device_id, time DESC);

-- Compress chunks older than 7 days
ALTER TABLE telemetry SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'site_id, device_id',
    timescaledb.compress_orderby = 'time DESC'
);
SELECT add_compression_policy('telemetry', INTERVAL '7 days');

-- Drop raw chunks older than 90 days
SELECT add_retention_policy('telemetry', INTERVAL '90 days');

-- ─────────────────────────────────────────────────────────────────
-- Continuous aggregates
-- ─────────────────────────────────────────────────────────────────

-- 15-minute aggregates
CREATE MATERIALIZED VIEW telemetry_15m
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('15 minutes', time) AS bucket,
    site_id,
    device_id,
    device_type,
    direction,
    avg(power_w)     AS avg_power_w,
    max(power_w)     AS max_power_w,
    min(power_w)     AS min_power_w,
    last(energy_kwh, time) - first(energy_kwh, time) AS delta_kwh,
    avg(soc_pct)     AS avg_soc_pct,
    count(*)         AS sample_count
FROM telemetry
GROUP BY bucket, site_id, device_id, device_type, direction
WITH NO DATA;

SELECT add_continuous_aggregate_policy('telemetry_15m',
    start_offset => INTERVAL '1 hour',
    end_offset   => INTERVAL '15 minutes',
    schedule_interval => INTERVAL '15 minutes'
);

-- Retain 2 years of 15-min aggregates
SELECT add_retention_policy('telemetry_15m', INTERVAL '2 years');

-- Hourly aggregates
CREATE MATERIALIZED VIEW telemetry_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS bucket,
    site_id,
    device_id,
    device_type,
    direction,
    avg(power_w)     AS avg_power_w,
    max(power_w)     AS max_power_w,
    last(energy_kwh, time) - first(energy_kwh, time) AS delta_kwh,
    avg(soc_pct)     AS avg_soc_pct
FROM telemetry
GROUP BY bucket, site_id, device_id, device_type, direction
WITH NO DATA;

SELECT add_continuous_aggregate_policy('telemetry_hourly',
    start_offset => INTERVAL '3 hours',
    end_offset   => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour'
);

-- Daily aggregates (no retention — keep forever)
CREATE MATERIALIZED VIEW telemetry_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS bucket,
    site_id,
    device_id,
    device_type,
    direction,
    avg(power_w)     AS avg_power_w,
    max(power_w)     AS max_power_w,
    last(energy_kwh, time) - first(energy_kwh, time) AS delta_kwh,
    avg(soc_pct)     AS avg_soc_pct
FROM telemetry
GROUP BY bucket, site_id, device_id, device_type, direction
WITH NO DATA;

SELECT add_continuous_aggregate_policy('telemetry_daily',
    start_offset => INTERVAL '2 days',
    end_offset   => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day'
);
