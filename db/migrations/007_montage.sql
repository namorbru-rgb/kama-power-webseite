-- KAMA Energy Platform — TimescaleDB Schema
-- Migration 007: Produktion / Montage tables
-- Written for the Montage Agent (KAMA-34).
-- Tracks assembly orders, technician resources, work positions, and acceptance protocols.

-- ─────────────────────────────────────────────────────────────────
-- Assembly orders (one per confirmed Auftrag)
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE montage_auftraege (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Reference to CRM order (kama_net_id from crm_auftraege)
    auftrag_id              TEXT NOT NULL,
    customer_name           TEXT NOT NULL DEFAULT '',
    -- solar | bess | vzev | combined
    project_type            TEXT NOT NULL DEFAULT 'solar'
        CHECK (project_type IN ('solar', 'bess', 'vzev', 'combined')),
    system_size_kwp         DOUBLE PRECISION,
    -- planned → materials_ready → assigned → in_progress → done | cancelled
    status                  TEXT NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned', 'materials_ready', 'assigned', 'in_progress', 'done', 'cancelled')),
    -- References app_technicians.id in KAMA-net
    assigned_technician_id  TEXT,
    planned_start_date      DATE,
    actual_start_date       DATE,
    actual_end_date         DATE,
    -- Set to true once procurement.delivered fires for this order
    materials_ready         BOOLEAN NOT NULL DEFAULT false,
    notes                   TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Unique: at most one active montage order per Auftrag
CREATE UNIQUE INDEX idx_montage_auftraege_auftrag ON montage_auftraege(auftrag_id)
    WHERE status NOT IN ('cancelled', 'done');

CREATE INDEX idx_montage_auftraege_status       ON montage_auftraege(status);
CREATE INDEX idx_montage_auftraege_technician   ON montage_auftraege(assigned_technician_id)
    WHERE assigned_technician_id IS NOT NULL;
CREATE INDEX idx_montage_auftraege_start        ON montage_auftraege(planned_start_date)
    WHERE status IN ('assigned', 'in_progress');

-- ─────────────────────────────────────────────────────────────────
-- Work positions / installation steps per montage order
-- Combines standard checklist steps + BOM material items
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE montage_positionen (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    montage_id      UUID NOT NULL REFERENCES montage_auftraege(id) ON DELETE CASCADE,
    -- Null for checklist steps that are not linked to a BOM article
    article_id      TEXT,
    description     TEXT NOT NULL,
    qty_required    DOUBLE PRECISION NOT NULL DEFAULT 1.0 CHECK (qty_required > 0),
    unit            TEXT NOT NULL DEFAULT 'Stk',
    -- Ordered display sequence
    sequence        INTEGER NOT NULL DEFAULT 0,
    -- open → in_progress → done | skipped
    status          TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'in_progress', 'done', 'skipped')),
    completed_at    TIMESTAMPTZ,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_montage_positionen_montage ON montage_positionen(montage_id);
CREATE INDEX idx_montage_positionen_status  ON montage_positionen(montage_id, status);

-- ─────────────────────────────────────────────────────────────────
-- Acceptance protocols (Abnahmeprotokolle)
-- Generated when all positions are completed.
-- Handed over to Meldewesen (KAMA-31) for regulatory submission.
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE montage_protokolle (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    montage_id          UUID NOT NULL REFERENCES montage_auftraege(id) ON DELETE CASCADE,
    auftrag_id          TEXT NOT NULL,
    customer_name       TEXT NOT NULL DEFAULT '',
    technician_id       TEXT,
    technician_name     TEXT,
    completed_positions INTEGER NOT NULL DEFAULT 0,
    total_positions     INTEGER NOT NULL DEFAULT 0,
    -- Full Markdown document
    body_markdown       TEXT NOT NULL DEFAULT '',
    -- When the protocol was handed over to Meldewesen
    handed_over_at      TIMESTAMPTZ,
    -- ID of the persisted record in KAMA-net (sops table)
    kama_net_id         TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_montage_protokolle_montage   ON montage_protokolle(montage_id);
CREATE INDEX idx_montage_protokolle_auftrag   ON montage_protokolle(auftrag_id);
CREATE INDEX idx_montage_protokolle_handover  ON montage_protokolle(handed_over_at)
    WHERE handed_over_at IS NOT NULL;
