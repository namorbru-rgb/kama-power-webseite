-- Migration 011: Agent Memory (Supabase Langzeitspeicher fuer Agent-Erinnerungen)
--
-- Tabellen:
--   agent_memory_items    — atomare Fakten/Erinnerungen pro Agent
--   agent_memory_events   — append-only Laufereignisse zur Nachvollziehbarkeit
--   agent_memory_snapshots — periodische Verdichtungen fuer schnelle Wiederherstellung
--
-- Zugriffsmodell: Supabase Service Role Key (serverseitig, nie im Frontend).
-- RLS ist standardmaessig aktiv; Service-Role umgeht RLS fuer technische Writer/Reader.

-- ---------------------------------------------------------------------------
-- 1) agent_memory_items
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_memory_items (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id         TEXT        NOT NULL,
    scope            TEXT        NOT NULL DEFAULT 'global',
    kind             TEXT        NOT NULL,                    -- e.g. 'fact', 'decision', 'preference'
    summary          TEXT        NOT NULL,
    details_json     JSONB,
    importance       SMALLINT    NOT NULL DEFAULT 5 CHECK (importance BETWEEN 1 AND 10),
    source_issue_id  TEXT,
    source_run_id    TEXT,
    valid_from       TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to         TIMESTAMPTZ,
    last_used_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Primaerer Query-Pfad: Agent + Scope sortiert nach Aktualitaet
CREATE INDEX IF NOT EXISTS idx_memory_items_agent_scope
    ON agent_memory_items (agent_id, scope, updated_at DESC);

-- Lookup nach Quell-Issue (fuer Issue-gebundene Erinnerungen)
CREATE INDEX IF NOT EXISTS idx_memory_items_source_issue
    ON agent_memory_items (source_issue_id)
    WHERE source_issue_id IS NOT NULL;

-- Rezency-basierter Zugriff
CREATE INDEX IF NOT EXISTS idx_memory_items_last_used
    ON agent_memory_items (last_used_at DESC);

-- ---------------------------------------------------------------------------
-- 2) agent_memory_events  (append-only)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_memory_events (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id         TEXT        NOT NULL,
    scope            TEXT        NOT NULL DEFAULT 'global',
    event_kind       TEXT        NOT NULL,                   -- e.g. 'status_change', 'decision', 'blocker'
    payload          JSONB,
    source_issue_id  TEXT,
    source_run_id    TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_memory_events_agent
    ON agent_memory_events (agent_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_events_source_issue
    ON agent_memory_events (source_issue_id)
    WHERE source_issue_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3) agent_memory_snapshots
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_memory_snapshots (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id         TEXT        NOT NULL,
    scope            TEXT        NOT NULL DEFAULT 'global',
    summary          TEXT        NOT NULL,
    items_json       JSONB,
    source_run_id    TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_memory_snapshots_agent
    ON agent_memory_snapshots (agent_id, scope, created_at DESC);
