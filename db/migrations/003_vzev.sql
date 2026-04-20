-- KAMA Energy Platform — TimescaleDB Schema
-- Migration 003: VZEV/LEG community billing model
-- Supports EnG Art. 17 (ZEV) and Art. 18 (VZEV) pilot on KAMA platform.

-- ─────────────────────────────────────────────────────────────────
-- VZEV community (Virtuelle Eigenverbrauchsgemeinschaft)
-- One community groups N participant sites under a single DSO contract.
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE vzev_communities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    -- Legal form: vzev (Art. 18) or zev (Art. 17)
    community_type  TEXT NOT NULL DEFAULT 'vzev' CHECK (community_type IN ('zev', 'vzev')),
    -- DSO responsible for this community (Thurnet AG, BKW, EKZ, etc.)
    dso_name        TEXT NOT NULL,
    -- DSO EIC code for machine-readable reporting
    dso_eic         TEXT,
    -- Netzbetreibergebiet (municipality or DSO-defined zone identifier)
    grid_zone_id    TEXT,
    -- Producer site — the site with the solar/BESS plant
    producer_site_id UUID NOT NULL REFERENCES sites(id),
    -- Swiss municipal code for regulatory reporting
    municipality_bfs TEXT,
    -- Date community was officially registered with DSO
    dso_registered_at DATE,
    -- Monthly DSO tariff for feed-in credit distribution (CHF/kWh)
    feed_in_tariff_chf_kwh DOUBLE PRECISION NOT NULL DEFAULT 0.11,
    -- Monthly community grid tariff (CHF/kWh) charged to participants for draw
    draw_tariff_chf_kwh DOUBLE PRECISION NOT NULL DEFAULT 0.22,
    active          BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_vzev_communities_producer ON vzev_communities(producer_site_id);

-- ─────────────────────────────────────────────────────────────────
-- VZEV membership (participant → community mapping)
-- Each participant has one site and one allocation share.
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE vzev_memberships (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    community_id    UUID NOT NULL REFERENCES vzev_communities(id) ON DELETE CASCADE,
    site_id         UUID NOT NULL REFERENCES sites(id),
    -- Human-readable participant label (tenant name, unit number, etc.)
    participant_name TEXT NOT NULL,
    -- Static allocation share (0.0–1.0). All active members must sum to 1.0.
    -- Used when allocation_method = 'static'.
    allocation_share DOUBLE PRECISION NOT NULL DEFAULT 0.0
        CHECK (allocation_share >= 0.0 AND allocation_share <= 1.0),
    -- static: fixed % from allocation_share
    -- proportional: share derived from participant's actual consumption each interval
    allocation_method TEXT NOT NULL DEFAULT 'proportional'
        CHECK (allocation_method IN ('static', 'proportional')),
    -- Contract validity window
    member_from     DATE NOT NULL,
    member_until    DATE,
    -- Contact for billing reports
    billing_email   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (community_id, site_id, member_from)
);

CREATE INDEX idx_vzev_memberships_community ON vzev_memberships(community_id);
CREATE INDEX idx_vzev_memberships_site ON vzev_memberships(site_id);

-- ─────────────────────────────────────────────────────────────────
-- VZEV billing periods
-- One row per community per calendar month, created by the billing engine.
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE vzev_billing_periods (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    community_id    UUID NOT NULL REFERENCES vzev_communities(id),
    -- First day of billing month (always day 1)
    period_start    DATE NOT NULL,
    -- Last day of billing month
    period_end      DATE NOT NULL,
    -- Total community solar production for the period (kWh)
    total_production_kwh DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    -- Total feed-in to grid (kWh) — what the community exported
    total_feed_in_kwh DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    -- Total draw from grid (kWh) — residual unmet demand
    total_draw_kwh DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    -- Draft: being calculated. Finalized: locked for invoicing.
    status          TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'finalized', 'reported')),
    -- Timestamp when DSO XML report was submitted
    dso_reported_at TIMESTAMPTZ,
    finalized_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (community_id, period_start)
);

CREATE INDEX idx_vzev_billing_community ON vzev_billing_periods(community_id, period_start DESC);

-- ─────────────────────────────────────────────────────────────────
-- VZEV invoice lines (per participant per billing period)
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE vzev_invoice_lines (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    billing_period_id UUID NOT NULL REFERENCES vzev_billing_periods(id) ON DELETE CASCADE,
    membership_id   UUID NOT NULL REFERENCES vzev_memberships(id),
    -- kWh of community solar allocated to this participant
    community_kwh   DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    -- kWh this participant drew from the grid (residual after community allocation)
    grid_draw_kwh   DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    -- kWh this participant fed into grid (if they have their own production)
    feed_in_kwh     DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    -- Financial summary (CHF)
    community_credit_chf DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    grid_draw_cost_chf   DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    feed_in_revenue_chf  DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    -- Net amount: negative = participant owes, positive = credit
    net_chf         DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (billing_period_id, membership_id)
);

CREATE INDEX idx_vzev_invoice_lines_period ON vzev_invoice_lines(billing_period_id);
CREATE INDEX idx_vzev_invoice_lines_membership ON vzev_invoice_lines(membership_id);

-- ─────────────────────────────────────────────────────────────────
-- VZEV interval allocations (15-min granularity audit trail)
-- Populated by the billing engine for each 15-min interval.
-- Used for dispute resolution and DSO reporting.
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE vzev_interval_allocations (
    time            TIMESTAMPTZ NOT NULL,
    community_id    UUID NOT NULL,
    membership_id   UUID NOT NULL REFERENCES vzev_memberships(id),
    -- Solar kWh allocated to this participant in this interval
    allocated_kwh   DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    -- Residual draw from grid for this participant
    grid_draw_kwh   DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    -- Effective allocation share used (may differ from static for proportional method)
    effective_share DOUBLE PRECISION NOT NULL DEFAULT 0.0
);

SELECT create_hypertable('vzev_interval_allocations', 'time',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists       => TRUE
);

CREATE INDEX IF NOT EXISTS ix_vzev_alloc_community_time
    ON vzev_interval_allocations (community_id, time DESC);

CREATE INDEX IF NOT EXISTS ix_vzev_alloc_membership_time
    ON vzev_interval_allocations (membership_id, time DESC);

-- Compress allocations older than 30 days (billing is always monthly)
ALTER TABLE vzev_interval_allocations SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'community_id, membership_id',
    timescaledb.compress_orderby   = 'time DESC'
);
SELECT add_compression_policy('vzev_interval_allocations', INTERVAL '30 days');

-- Keep 7 years (Swiss accounting retention requirement)
SELECT add_retention_policy('vzev_interval_allocations', INTERVAL '7 years');
