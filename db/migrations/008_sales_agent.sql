-- KAMA Energy Platform — TimescaleDB Schema
-- Migration 008: Sales & Lead Agent — Angebote (quotes) + follow-up tracking
-- Written by Sales-Lead Agent (KAMA-27)

-- ─────────────────────────────────────────────────────────────────
-- Angebote (sales quotes)
-- One quote per lead inquiry; tracks lifecycle from draft → sent → accepted
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE sales_quotes (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Links back to the source lead in crm_anfragen
    anfrage_kama_net_id     TEXT NOT NULL REFERENCES crm_anfragen(kama_net_id) ON DELETE CASCADE,
    customer_name           TEXT NOT NULL,
    customer_email          TEXT,
    -- solar | bess | vzev | combined
    project_type            TEXT NOT NULL DEFAULT 'solar'
        CHECK (project_type IN ('solar', 'bess', 'vzev', 'combined')),
    -- Calculated system size from Solar-Kalkulator
    system_size_kwp         DOUBLE PRECISION,
    -- Annual yield estimate in kWh
    annual_yield_kwh        DOUBLE PRECISION,
    -- Total offer value in CHF (net)
    quote_value_chf         DOUBLE PRECISION,
    -- draft | sent | accepted | rejected | expired
    status                  TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'sent', 'accepted', 'rejected', 'expired')),
    sent_at                 TIMESTAMPTZ,
    accepted_at             TIMESTAMPTZ,
    rejected_at             TIMESTAMPTZ,
    -- Quote valid for 30 days by default
    expires_at              TIMESTAMPTZ,
    -- Markdown body of the offer document
    body_markdown           TEXT,
    -- Message-ID of the sent email (for reply tracking)
    email_message_id        TEXT,
    -- If this quote was synced back to KAMA-net
    kama_net_quote_id       TEXT,
    notes                   TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_sales_quotes_anfrage   ON sales_quotes(anfrage_kama_net_id);
CREATE INDEX idx_sales_quotes_status    ON sales_quotes(status);
CREATE INDEX idx_sales_quotes_sent      ON sales_quotes(sent_at DESC NULLS LAST);

-- ─────────────────────────────────────────────────────────────────
-- Follow-up schedule
-- Agent schedules one follow-up 7 days after initial send.
-- Additional follow-ups possible (attempt_number > 1).
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE sales_followups (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    quote_id                UUID NOT NULL REFERENCES sales_quotes(id) ON DELETE CASCADE,
    anfrage_kama_net_id     TEXT NOT NULL,
    -- When the follow-up should be sent
    scheduled_at            TIMESTAMPTZ NOT NULL,
    sent_at                 TIMESTAMPTZ,
    -- pending | sent | skipped | cancelled
    status                  TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'sent', 'skipped', 'cancelled')),
    -- 1 = first follow-up (7d), 2 = second (14d), etc.
    attempt_number          INT NOT NULL DEFAULT 1,
    -- Message-ID of the follow-up email
    email_message_id        TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Partial index: only pending follow-ups need scheduling lookups
CREATE INDEX idx_sales_followups_scheduled  ON sales_followups(scheduled_at)
    WHERE status = 'pending';
CREATE INDEX idx_sales_followups_quote      ON sales_followups(quote_id);
