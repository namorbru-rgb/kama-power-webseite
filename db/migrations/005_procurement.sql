-- KAMA Energy Platform — TimescaleDB Schema
-- Migration 005: Procurement / Beschaffung tables
-- Written for the Procurement Agent (KAMA-29).
-- Tracks BOMs, supplier orders, and individual order line items.

-- ─────────────────────────────────────────────────────────────────
-- Bill of Materials per order (sourced from KAMA-net app_articles)
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE procurement_bom (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- kama_net_id from crm_auftraege
    auftrag_id      TEXT NOT NULL,
    -- article ID from KAMA-net app_articles
    article_id      TEXT NOT NULL,
    article_name    TEXT NOT NULL,
    qty_required    DOUBLE PRECISION NOT NULL CHECK (qty_required > 0),
    unit            TEXT NOT NULL DEFAULT 'Stk',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_procurement_bom_auftrag ON procurement_bom(auftrag_id);
CREATE UNIQUE INDEX idx_procurement_bom_unique ON procurement_bom(auftrag_id, article_id);

-- ─────────────────────────────────────────────────────────────────
-- Supplier orders (one per supplier per order)
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE procurement_orders (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    auftrag_id          TEXT NOT NULL,
    -- andercore | tritec | mph | solarmarkt | other
    supplier            TEXT NOT NULL,
    -- draft → sent → confirmed → delivered | cancelled
    status              TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'sent', 'confirmed', 'delivered', 'cancelled')),
    ordered_at          TIMESTAMPTZ,
    expected_delivery   DATE,
    confirmed_at        TIMESTAMPTZ,
    delivered_at        TIMESTAMPTZ,
    -- SMTP Message-ID for thread tracking
    email_message_id    TEXT,
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_procurement_orders_auftrag ON procurement_orders(auftrag_id);
CREATE INDEX idx_procurement_orders_status  ON procurement_orders(status);
CREATE INDEX idx_procurement_orders_delivery ON procurement_orders(expected_delivery)
    WHERE status IN ('sent', 'confirmed');

-- ─────────────────────────────────────────────────────────────────
-- Line items per supplier order
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE procurement_order_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id        UUID NOT NULL REFERENCES procurement_orders(id) ON DELETE CASCADE,
    article_id      TEXT NOT NULL,
    article_name    TEXT NOT NULL,
    qty_ordered     DOUBLE PRECISION NOT NULL CHECK (qty_ordered > 0),
    unit_price_chf  DOUBLE PRECISION,
    unit            TEXT NOT NULL DEFAULT 'Stk',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_procurement_items_order ON procurement_order_items(order_id);
