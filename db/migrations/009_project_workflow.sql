-- KAMA Energy Platform — TimescaleDB Schema
-- Migration 009: Projekt- & Workflow-Engine — Projekte, Schritte, Abhängigkeiten
-- Written by CTO Agent (KAMA-28)
-- Herzstück der KI-Prozesssteuerung: jeder Auftrag bekommt einen Workflow mit
-- nummerierten Schritten, definierten Abhängigkeiten und Paperclip-Issue-Tracking.

-- ─────────────────────────────────────────────────────────────────
-- project_workflows
-- One workflow per confirmed order (crm_auftraege). Tracks the
-- overall project state and maps to the Paperclip project/goal.
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE project_workflows (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Source order in our CRM mirror
    auftrag_kama_net_id     TEXT NOT NULL REFERENCES crm_auftraege(kama_net_id) ON DELETE CASCADE,
    -- Human-readable project name (e.g. "Solar 12kWp — Müller AG, Güttingen")
    name                    TEXT NOT NULL,
    -- solar | bess | vzev | combined — determines which step template is used
    project_type            TEXT NOT NULL DEFAULT 'solar'
        CHECK (project_type IN ('solar', 'bess', 'vzev', 'combined')),
    -- pending: created, not yet started
    -- active: at least one step in_progress or done
    -- completed: all steps done
    -- cancelled: order cancelled
    -- on_hold: waiting for external input
    status                  TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'active', 'completed', 'cancelled', 'on_hold')),
    -- Paperclip goal/project tracking (optional; set when first Paperclip issue created)
    paperclip_goal_id       TEXT,
    -- KAMA-net project ID for fm_projektfortschritt sync
    kama_net_project_id     TEXT,
    -- System size in kWp (for solar) or kWh (for BESS) — drives BOM & timeline
    system_size             DOUBLE PRECISION,
    -- Target completion date from contract
    target_completion_date  DATE,
    -- Actual completion date (set when status → completed)
    actual_completion_date  DATE,
    notes                   TEXT,
    started_at              TIMESTAMPTZ,
    completed_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_project_workflows_auftrag ON project_workflows(auftrag_kama_net_id);
CREATE INDEX idx_project_workflows_status  ON project_workflows(status);
CREATE INDEX idx_project_workflows_type    ON project_workflows(project_type);
CREATE INDEX idx_project_workflows_updated ON project_workflows(updated_at DESC);

-- ─────────────────────────────────────────────────────────────────
-- workflow_step_templates
-- Canonical list of steps per project_type. Seeded once.
-- The engine uses this to generate workflow_steps for each project.
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE workflow_step_templates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_type    TEXT NOT NULL DEFAULT 'solar',
    -- Ascending execution order within the project
    sequence        INT NOT NULL,
    -- Machine-readable key (e.g. "materialbeschaffung")
    step_key        TEXT NOT NULL,
    -- Human-readable German title
    title           TEXT NOT NULL,
    -- Optional description / instructions for the agent
    description     TEXT,
    -- Which Paperclip agent role handles this step
    -- agent_role values: 'ceo' | 'cto' | 'procurement' | 'montage' | 'meldewesen'
    agent_role      TEXT NOT NULL DEFAULT 'cto',
    -- Estimated duration in working days (used to compute target dates)
    estimated_days  INT NOT NULL DEFAULT 1,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_type, step_key)
);

CREATE INDEX idx_step_templates_type_seq ON workflow_step_templates(project_type, sequence);

-- ─────────────────────────────────────────────────────────────────
-- workflow_step_template_deps
-- Prerequisite relationships between step templates.
-- "step B can only start after step A is done."
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE workflow_step_template_deps (
    project_type    TEXT NOT NULL,
    step_key        TEXT NOT NULL,        -- the dependent step (B)
    requires_key    TEXT NOT NULL,        -- must be done first (A)
    PRIMARY KEY (project_type, step_key, requires_key),
    FOREIGN KEY (project_type, step_key)
        REFERENCES workflow_step_templates(project_type, step_key) ON DELETE CASCADE,
    FOREIGN KEY (project_type, requires_key)
        REFERENCES workflow_step_templates(project_type, step_key) ON DELETE CASCADE
);

-- ─────────────────────────────────────────────────────────────────
-- workflow_steps
-- Instantiated steps for each project_workflow.
-- status lifecycle: pending → ready → in_progress → done | skipped | blocked
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE workflow_steps (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id             UUID NOT NULL REFERENCES project_workflows(id) ON DELETE CASCADE,
    -- The template this step was instantiated from
    step_key                TEXT NOT NULL,
    sequence                INT NOT NULL,
    title                   TEXT NOT NULL,
    description             TEXT,
    agent_role              TEXT NOT NULL,
    -- pending: prerequisites not yet met
    -- ready: all prerequisites done, can be started
    -- in_progress: checked out by agent / Paperclip issue active
    -- done: completed successfully
    -- skipped: explicitly bypassed (e.g. netzbetreiber already registered)
    -- blocked: manual blocker flagged
    status                  TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'ready', 'in_progress', 'done', 'skipped', 'blocked')),
    -- Paperclip issue tracking
    paperclip_issue_id      TEXT,
    paperclip_issue_key     TEXT,       -- e.g. "KAMA-45"
    paperclip_agent_id      TEXT,
    -- Target date computed from workflow start + accumulated estimated_days
    target_date             DATE,
    -- Actual start/finish
    started_at              TIMESTAMPTZ,
    completed_at            TIMESTAMPTZ,
    -- Blocker description (when status = blocked)
    blocker_note            TEXT,
    notes                   TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workflow_id, step_key)
);

CREATE INDEX idx_workflow_steps_workflow   ON workflow_steps(workflow_id);
CREATE INDEX idx_workflow_steps_status     ON workflow_steps(status);
CREATE INDEX idx_workflow_steps_issue      ON workflow_steps(paperclip_issue_id);
CREATE INDEX idx_workflow_steps_seq        ON workflow_steps(workflow_id, sequence);

-- ─────────────────────────────────────────────────────────────────
-- workflow_step_deps
-- Instantiated dependency edges (mirrors template deps per project).
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE workflow_step_deps (
    workflow_id     UUID NOT NULL REFERENCES project_workflows(id) ON DELETE CASCADE,
    step_key        TEXT NOT NULL,        -- dependent step
    requires_key    TEXT NOT NULL,        -- must be done first
    PRIMARY KEY (workflow_id, step_key, requires_key)
);

CREATE INDEX idx_workflow_step_deps_workflow ON workflow_step_deps(workflow_id);

-- ─────────────────────────────────────────────────────────────────
-- workflow_events
-- Immutable audit log: every status transition, comment, or sync event.
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE workflow_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id     UUID NOT NULL REFERENCES project_workflows(id) ON DELETE CASCADE,
    step_id         UUID REFERENCES workflow_steps(id) ON DELETE SET NULL,
    -- Types: workflow_created | step_ready | step_started | step_done |
    --        step_skipped | step_blocked | workflow_completed |
    --        paperclip_issue_created | kama_net_synced | kafka_event_received
    event_type      TEXT NOT NULL,
    -- JSON payload (event data, e.g. old/new status, issue key, agent ID)
    payload         JSONB NOT NULL DEFAULT '{}',
    -- Source: kafka | paperclip | api | manual
    source          TEXT NOT NULL DEFAULT 'kafka',
    -- Kafka message offset if applicable
    kafka_offset    BIGINT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_workflow_events_workflow   ON workflow_events(workflow_id);
CREATE INDEX idx_workflow_events_step       ON workflow_events(step_id);
CREATE INDEX idx_workflow_events_type       ON workflow_events(event_type);
CREATE INDEX idx_workflow_events_created    ON workflow_events(created_at DESC);

-- ─────────────────────────────────────────────────────────────────
-- SEED: Solar workflow step templates (9 steps per KAMA-28)
-- ─────────────────────────────────────────────────────────────────

INSERT INTO workflow_step_templates
    (project_type, sequence, step_key, title, description, agent_role, estimated_days)
VALUES
    -- Step 1: Internal project approval
    ('solar', 1, 'projektfreigabe_intern',
     'Projektfreigabe intern',
     'Auftrag prüfen, interne Freigabe erteilen. Projekt in KAMA-net anlegen.',
     'ceo', 1),

    -- Step 2: Planning (design, schema, permit application)
    ('solar', 2, 'planung',
     'Planung — Auslegung, Schema, Baugenehmigung',
     'Systemauslegung berechnen, Einlinienschema erstellen, Baubewilligungsgesuch vorbereiten.',
     'cto', 5),

    -- Step 3: Material procurement
    ('solar', 3, 'materialbeschaffung',
     'Materialbeschaffung → Procurement Agent',
     'BOM erstellen und Bestellung bei Lieferanten auslösen. Procurement Agent übernimmt.',
     'procurement', 3),

    -- Step 4: Grid operator registration (parallel to step 3)
    ('solar', 4, 'netzbetreiber_anmeldung',
     'Netzbetreiber-Anmeldung (TAG)',
     'Technische Anschlussbedingungen beim VNB einreichen. Anmeldung vor Baubeginn Pflicht.',
     'meldewesen', 2),

    -- Step 5: Schedule assembly (requires material)
    ('solar', 5, 'montage_terminieren',
     'Montage terminieren',
     'Montagedatum festlegen, Monteur zuteilen, Material-Checkliste prüfen.',
     'montage', 1),

    -- Step 6: Schedule electrical installation (requires material)
    ('solar', 6, 'elektro_terminieren',
     'Elektroinstallation terminieren',
     'Elektriker koordinieren, Anschluss-Termin beim Netzbetreiber bestätigen.',
     'cto', 1),

    -- Step 7: Commissioning + acceptance (requires steps 5 AND 6)
    ('solar', 7, 'ibn_abnahme',
     'IBN + Abnahme',
     'Inbetriebnahme durchführen, Abnahmeprotokoll erstellen, Anlage testen.',
     'montage', 2),

    -- Step 8: Regulatory notifications (requires commissioning)
    ('solar', 8, 'meldungen',
     'Meldungen — TAG, Pronovo, VNB, EIV',
     'Installationsanzeige, HKN-Registrierung bei Pronovo, EIV-Antrag einreichen.',
     'meldewesen', 5),

    -- Step 9: Project closure + documentation
    ('solar', 9, 'abschluss',
     'Abschluss + Dokumentation',
     'Alle Dokumente in Dropbox ablegen, KAMA-net schliessen, Rechnung auslösen.',
     'cto', 2);

-- ─────────────────────────────────────────────────────────────────
-- SEED: Solar dependency edges
-- ─────────────────────────────────────────────────────────────────

INSERT INTO workflow_step_template_deps (project_type, step_key, requires_key) VALUES
    -- Planung requires Projektfreigabe
    ('solar', 'planung',                 'projektfreigabe_intern'),
    -- Materialbeschaffung requires Planung
    ('solar', 'materialbeschaffung',     'planung'),
    -- Netzbetreiber-Anmeldung requires Planung (parallel to Materialbeschaffung)
    ('solar', 'netzbetreiber_anmeldung', 'planung'),
    -- Montage terminieren requires Materialbeschaffung (Material must be delivered)
    ('solar', 'montage_terminieren',     'materialbeschaffung'),
    -- Elektro terminieren requires Materialbeschaffung
    ('solar', 'elektro_terminieren',     'materialbeschaffung'),
    -- IBN + Abnahme requires both Montage AND Elektro
    ('solar', 'ibn_abnahme',             'montage_terminieren'),
    ('solar', 'ibn_abnahme',             'elektro_terminieren'),
    -- Meldungen requires Abnahme (Pronovo only after commissioning)
    ('solar', 'meldungen',               'ibn_abnahme'),
    -- Abschluss requires all Meldungen complete
    ('solar', 'abschluss',               'meldungen');

-- ─────────────────────────────────────────────────────────────────
-- SEED: BESS workflow step templates (simplified 6-step)
-- ─────────────────────────────────────────────────────────────────

INSERT INTO workflow_step_templates
    (project_type, sequence, step_key, title, description, agent_role, estimated_days)
VALUES
    ('bess', 1, 'projektfreigabe_intern',
     'Projektfreigabe intern',
     'Auftrag prüfen, interne Freigabe erteilen.',
     'ceo', 1),
    ('bess', 2, 'planung',
     'Planung — Systemdimensionierung, Schutzkonzept',
     'BESS-Auslegung, Schutzkonzept, Netzgenehmigung.',
     'cto', 5),
    ('bess', 3, 'materialbeschaffung',
     'Materialbeschaffung',
     'BOM erstellen, BESS-Einheit und Wechselrichter bestellen.',
     'procurement', 7),
    ('bess', 4, 'montage_inbetriebnahme',
     'Montage + IBN',
     'BESS installieren, Inbetriebnahme, Zertifizierung.',
     'montage', 3),
    ('bess', 5, 'netzbetreiber_meldung',
     'Netzbetreiber-Meldung + EIV',
     'Installationsanzeige einreichen, EIV-Antrag stellen.',
     'meldewesen', 5),
    ('bess', 6, 'abschluss',
     'Abschluss + Dokumentation',
     'Dokumente in Dropbox, KAMA-net schliessen, Rechnung.',
     'cto', 2);

INSERT INTO workflow_step_template_deps (project_type, step_key, requires_key) VALUES
    ('bess', 'planung',                 'projektfreigabe_intern'),
    ('bess', 'materialbeschaffung',     'planung'),
    ('bess', 'montage_inbetriebnahme',  'materialbeschaffung'),
    ('bess', 'netzbetreiber_meldung',   'montage_inbetriebnahme'),
    ('bess', 'abschluss',               'netzbetreiber_meldung');

-- ─────────────────────────────────────────────────────────────────
-- updated_at triggers (reuse pattern from existing migrations)
-- ─────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_project_workflows_updated_at
    BEFORE UPDATE ON project_workflows
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_workflow_steps_updated_at
    BEFORE UPDATE ON workflow_steps
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
