-- KAMA Energy Platform — TimescaleDB Schema
-- Migration 004: KAMA-net CRM read-side tables + BESS field inventory
-- Synced from KAMA-net (app_projects, app_orders) via FM-Sync job.
-- These tables are append/upsert-only — never modified by the API directly.

-- ─────────────────────────────────────────────────────────────────
-- Anfragen (leads / project inquiries — KAMA-net app_projects mirror)
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE crm_anfragen (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Original KAMA-net record ID for dedup/sync
    kama_net_id     TEXT UNIQUE NOT NULL,
    title           TEXT NOT NULL,
    customer_name   TEXT NOT NULL,
    -- solar | bess | vzev | combined
    project_type    TEXT NOT NULL DEFAULT 'solar'
        CHECK (project_type IN ('solar', 'bess', 'vzev', 'combined')),
    -- new | contacted | qualified | quoted | won | lost | cancelled
    status          TEXT NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'contacted', 'qualified', 'quoted', 'won', 'lost', 'cancelled')),
    -- Hot/Warm/Cold computed by sync job from last_contact_at + status
    -- hot: contacted in last 7d AND qualified/quoted
    -- warm: contacted in last 30d
    -- cold: >30d since contact or no contact
    temperature     TEXT NOT NULL DEFAULT 'cold'
        CHECK (temperature IN ('hot', 'warm', 'cold')),
    estimated_value_chf DOUBLE PRECISION,
    last_contact_at TIMESTAMPTZ,
    expected_close_date DATE,
    assigned_to     TEXT,
    municipality    TEXT,
    notes           TEXT,
    -- When this row was last synced from KAMA-net
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_crm_anfragen_status ON crm_anfragen(status);
CREATE INDEX idx_crm_anfragen_temperature ON crm_anfragen(temperature);
CREATE INDEX idx_crm_anfragen_project_type ON crm_anfragen(project_type);
CREATE INDEX idx_crm_anfragen_updated ON crm_anfragen(updated_at DESC);

-- ─────────────────────────────────────────────────────────────────
-- Aufträge (orders — KAMA-net app_orders mirror)
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE crm_auftraege (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kama_net_id     TEXT UNIQUE NOT NULL,
    -- May reference a known KAMA-net inquiry; nullable for direct orders
    anfrage_kama_net_id TEXT REFERENCES crm_anfragen(kama_net_id) ON DELETE SET NULL,
    title           TEXT NOT NULL,
    customer_name   TEXT NOT NULL,
    -- solar | bess
    project_type    TEXT NOT NULL DEFAULT 'solar'
        CHECK (project_type IN ('solar', 'bess', 'vzev', 'combined')),
    -- new | planning | ordered | installation | commissioning | completed | cancelled
    status          TEXT NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'planning', 'ordered', 'installation', 'commissioning', 'completed', 'cancelled')),
    contract_value_chf DOUBLE PRECISION,
    -- System size, e.g. kWp for solar, kWh for BESS
    system_size_kwp DOUBLE PRECISION,
    expected_completion_date DATE,
    actual_completion_date   DATE,
    -- If a BESS site was already provisioned in our platform
    site_id         UUID REFERENCES sites(id) ON DELETE SET NULL,
    assigned_to     TEXT,
    notes           TEXT,
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_crm_auftraege_status ON crm_auftraege(status);
CREATE INDEX idx_crm_auftraege_project_type ON crm_auftraege(project_type);
CREATE INDEX idx_crm_auftraege_updated ON crm_auftraege(updated_at DESC);

-- ─────────────────────────────────────────────────────────────────
-- BESS Feldbestand (field installations)
-- Tracks all 13+ deployed BESS systems.
-- May link to sites table for live telemetry; or standalone record
-- for systems not yet connected to the monitoring platform.
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE bess_installations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Human-readable name, e.g. "Landwirt Müller, Thal SG"
    name            TEXT NOT NULL,
    customer_name   TEXT NOT NULL,
    municipality    TEXT,
    -- Link to monitored site if already onboarded
    site_id         UUID REFERENCES sites(id) ON DELETE SET NULL,
    -- Link to originating order if tracked in CRM
    auftrag_kama_net_id TEXT REFERENCES crm_auftraege(kama_net_id) ON DELETE SET NULL,
    -- Hardware specs
    capacity_kwh    DOUBLE PRECISION NOT NULL,
    power_kw        DOUBLE PRECISION NOT NULL,
    manufacturer    TEXT,
    model           TEXT,
    serial_number   TEXT,
    -- operational | commissioning | maintenance | offline | decommissioned
    status          TEXT NOT NULL DEFAULT 'operational'
        CHECK (status IN ('operational', 'commissioning', 'maintenance', 'offline', 'decommissioned')),
    -- IBN = Inbetriebnahme (commissioning)
    ibn_planned_date DATE,
    ibn_actual_date  DATE,
    -- Warranty expiry
    warranty_until   DATE,
    -- Open service tickets / notes
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_bess_installations_status ON bess_installations(status);
CREATE INDEX idx_bess_installations_site ON bess_installations(site_id);
