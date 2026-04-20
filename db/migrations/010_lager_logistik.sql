-- KAMA Energy Platform — TimescaleDB Schema
-- Migration 010: Lager & Logistik tables
-- Written for the Lager-Logistik Agent (KAMA-30).
-- Tracks warehouse deliveries, goods receipts, and inventory levels.

-- ─────────────────────────────────────────────────────────────────
-- Pending and confirmed deliveries
-- lifecycle: geplant → angekuendigt → eingetroffen → bestaetigt
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE lager_lieferungen (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Reference to CRM order
    auftrag_id              TEXT NOT NULL,
    -- Procurement order identifier
    order_id                TEXT NOT NULL,
    supplier                TEXT NOT NULL DEFAULT '',
    -- geplant: order placed, not yet arrived
    -- angekuendigt: warehouse notified via Telegram
    -- eingetroffen: procurement.delivered event received
    -- bestaetigt: warehouse employee confirmed receipt
    status                  TEXT NOT NULL DEFAULT 'geplant'
        CHECK (status IN ('geplant', 'angekuendigt', 'eingetroffen', 'bestaetigt')),
    expected_delivery       DATE,
    -- Timestamp from procurement.delivered event
    eingang_at              TIMESTAMPTZ,
    -- When warehouse employee confirmed via reply
    bestaetigt_at           TIMESTAMPTZ,
    -- Telegram sender id or name who confirmed
    bestaetigt_by           TEXT,
    -- When we sent the advance notification (geplant → angekuendigt)
    vorankuendigung_sent_at TIMESTAMPTZ,
    -- When we sent the arrival notification (eingetroffen)
    eingang_notification_sent_at TIMESTAMPTZ,
    notes                   TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One active delivery record per procurement order
CREATE UNIQUE INDEX idx_lager_lieferungen_order ON lager_lieferungen(order_id)
    WHERE status NOT IN ('bestaetigt');

CREATE INDEX idx_lager_lieferungen_auftrag ON lager_lieferungen(auftrag_id);
CREATE INDEX idx_lager_lieferungen_status  ON lager_lieferungen(status);

-- ─────────────────────────────────────────────────────────────────
-- Warehouse inventory (current stock levels)
-- Updated on each confirmed goods receipt.
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE lager_bestand (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id          TEXT NOT NULL,
    article_name        TEXT NOT NULL DEFAULT '',
    qty                 DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (qty >= 0),
    unit                TEXT NOT NULL DEFAULT 'Stk',
    last_eingang_at     TIMESTAMPTZ,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_lager_bestand_article ON lager_bestand(article_id);

-- ─────────────────────────────────────────────────────────────────
-- Goods receipt line items (what arrived per delivery)
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE lager_eingang_positionen (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lieferung_id    UUID NOT NULL REFERENCES lager_lieferungen(id) ON DELETE CASCADE,
    article_id      TEXT NOT NULL,
    article_name    TEXT NOT NULL DEFAULT '',
    qty_received    DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (qty_received >= 0),
    unit            TEXT NOT NULL DEFAULT 'Stk',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_lager_eingang_positionen_lieferung ON lager_eingang_positionen(lieferung_id);
CREATE INDEX idx_lager_eingang_positionen_article   ON lager_eingang_positionen(article_id);
