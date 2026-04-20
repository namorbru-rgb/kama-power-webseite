-- KAMA Energy Platform — TimescaleDB Schema
-- Migration 006: Communication Agent tables
-- Written for the Communication Agent (KAMA-32).
-- Tracks all outbound/inbound messages across channels (email, telegram, whatsapp),
-- thread context for reply tracking, and AI-generated SOPs.

-- ─────────────────────────────────────────────────────────────────
-- Communication messages (email / telegram / whatsapp / internal)
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE comm_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- email | telegram | whatsapp | internal
    channel         TEXT NOT NULL
        CHECK (channel IN ('email', 'telegram', 'whatsapp', 'internal')),
    -- outbound | inbound
    direction       TEXT NOT NULL
        CHECK (direction IN ('outbound', 'inbound')),
    -- For email: RFC-5321 Message-ID. For telegram: message_id integer as text.
    external_id     TEXT,
    -- Thread / conversation grouping key
    thread_id       UUID,
    -- Sender address / chat_id
    sender          TEXT,
    -- Recipient address / chat_id (comma-separated for multi)
    recipient       TEXT,
    subject         TEXT,
    body            TEXT NOT NULL,
    -- JSON metadata (e.g. headers, parse results, supplier, auftrag_id)
    metadata        JSONB NOT NULL DEFAULT '{}',
    -- draft → sent → delivered | read | replied | failed
    status          TEXT NOT NULL DEFAULT 'sent'
        CHECK (status IN ('draft', 'sent', 'delivered', 'read', 'replied', 'failed')),
    sent_at         TIMESTAMPTZ,
    received_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

SELECT create_hypertable('comm_messages', 'created_at', if_not_exists => TRUE);

CREATE INDEX idx_comm_messages_channel    ON comm_messages(channel);
CREATE INDEX idx_comm_messages_direction  ON comm_messages(direction);
CREATE INDEX idx_comm_messages_thread     ON comm_messages(thread_id);
CREATE INDEX idx_comm_messages_external   ON comm_messages(external_id);
CREATE INDEX idx_comm_messages_status     ON comm_messages(status);

-- ─────────────────────────────────────────────────────────────────
-- Conversation threads (groups related messages)
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE comm_threads (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel         TEXT NOT NULL,
    -- Subject or topic line for the thread
    topic           TEXT NOT NULL,
    -- The external entity (email address, telegram chat_id, supplier key)
    participant     TEXT,
    -- Awaiting response from this actor (null = closed)
    awaiting_reply_from TEXT,
    -- Context (auftrag_id, supplier, etc.) as JSON
    context         JSONB NOT NULL DEFAULT '{}',
    -- open | resolved | escalated
    state           TEXT NOT NULL DEFAULT 'open'
        CHECK (state IN ('open', 'resolved', 'escalated')),
    opened_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_comm_threads_channel   ON comm_threads(channel);
CREATE INDEX idx_comm_threads_state     ON comm_threads(state);
CREATE INDEX idx_comm_threads_participant ON comm_threads(participant);

-- ─────────────────────────────────────────────────────────────────
-- Standard Operating Procedures (AI-generated, stored in KAMA-net)
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE comm_sops (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    -- The domain area (procurement, logistics, installation, admin, etc.)
    domain          TEXT NOT NULL,
    -- Markdown body of the SOP
    body            TEXT NOT NULL,
    -- Supabase record id after sync
    kama_net_id     TEXT,
    -- Extracted from which conversation / thread
    source_thread_id UUID REFERENCES comm_threads(id),
    version         INT NOT NULL DEFAULT 1,
    created_by      TEXT NOT NULL DEFAULT 'communication-agent',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_comm_sops_domain ON comm_sops(domain);
CREATE INDEX idx_comm_sops_kama_net ON comm_sops(kama_net_id);
