-- KAMA Energy Platform — TimescaleDB Schema
-- Migration 002: Grid signals hypertable (DSO-agnostic canonical model)

-- ─────────────────────────────────────────────────────────────────
-- Canonical grid_signals hypertable
-- Populated by the grid-normalizer service from grid.normalized topic.
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS grid_signals (
    -- Interval start — partition key for TimescaleDB
    timestamp       TIMESTAMPTZ         NOT NULL,
    -- DSO identifier (EIC code or internal short-name)
    dso_id          TEXT                NOT NULL,
    -- Semantic signal category: IMBALANCE_PRICE | TARIFF | LOAD | CAPACITY | CONGESTION | FREQUENCY | GENERATION
    signal_type     TEXT                NOT NULL,
    -- Measured / forecast value
    value           DOUBLE PRECISION    NOT NULL,
    -- Physical unit (MW, EUR/MWh, CHF/kWh, Hz, %)
    unit            TEXT                NOT NULL,
    -- ENTSO-E bidding zone or grid node EIC code
    location_eic    TEXT                NOT NULL,
    -- Data origin: entso-e | swissgrid | ewz | bkw | elcom
    source          TEXT                NOT NULL,
    -- Confidence: measured | estimated | forecast
    quality         TEXT                NOT NULL,
    -- ISO 8601 duration (nullable for point-in-time signals)
    resolution      TEXT,
    -- Interval end (nullable for open-ended or point-in-time signals)
    period_end      TIMESTAMPTZ,
    -- Source-specific metadata (psr_type, tariff_zone, etc.)
    meta            JSONB
);

SELECT create_hypertable('grid_signals', 'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists       => TRUE
);

-- ─────────────────────────────────────────────────────────────────
-- Indexes — optimised for optimization engine query patterns
-- ─────────────────────────────────────────────────────────────────

-- Query by signal type and time (most common: latest imbalance prices)
CREATE INDEX IF NOT EXISTS ix_grid_signals_type_ts
    ON grid_signals (signal_type, timestamp DESC);

-- Query by grid location and time (congestion / capacity signals)
CREATE INDEX IF NOT EXISTS ix_grid_signals_location_ts
    ON grid_signals (location_eic, timestamp DESC);

-- Query by source (for data quality auditing)
CREATE INDEX IF NOT EXISTS ix_grid_signals_source_ts
    ON grid_signals (source, timestamp DESC);

-- ─────────────────────────────────────────────────────────────────
-- Compression — keep storage lean for the time-series data
-- ─────────────────────────────────────────────────────────────────

ALTER TABLE grid_signals SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'signal_type, location_eic, source',
    timescaledb.compress_orderby   = 'timestamp DESC'
);

SELECT add_compression_policy('grid_signals', INTERVAL '7 days');

-- Retain 2 years of raw grid signals
SELECT add_retention_policy('grid_signals', INTERVAL '2 years');
