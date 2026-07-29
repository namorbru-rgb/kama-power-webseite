-- KAMAA_SECTION69_RESTORE_DRILL_SNAPSHOT_V1
-- fixture_id: kamaa-section69-valid-2026-07-29
-- schema_version: 1
-- expected_marker: KAMAA-SECTION69-RESTORE-MARKER-001
BEGIN;

CREATE TABLE restore_drill_manifest (
  fixture_id text PRIMARY KEY,
  schema_version integer NOT NULL,
  expected_marker text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE restore_drill_sites (
  id uuid PRIMARY KEY,
  name text NOT NULL,
  active boolean NOT NULL DEFAULT true
);

CREATE TABLE restore_drill_events (
  id uuid PRIMARY KEY,
  site_id uuid NOT NULL REFERENCES restore_drill_sites(id) ON DELETE CASCADE,
  marker text NOT NULL,
  event_type text NOT NULL,
  observed_at timestamptz NOT NULL
);

INSERT INTO restore_drill_manifest (fixture_id, schema_version, expected_marker)
VALUES (
  'kamaa-section69-valid-2026-07-29',
  1,
  'KAMAA-SECTION69-RESTORE-MARKER-001'
);

INSERT INTO restore_drill_sites (id, name, active)
VALUES
  ('11111111-1111-4111-8111-111111111111', 'KAMAA Section 69 Drill Site A', true),
  ('22222222-2222-4222-8222-222222222222', 'KAMAA Section 69 Drill Site B', true);

INSERT INTO restore_drill_events (id, site_id, marker, event_type, observed_at)
VALUES
  (
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    '11111111-1111-4111-8111-111111111111',
    'KAMAA-SECTION69-RESTORE-MARKER-001',
    'snapshot_imported',
    '2026-07-29T00:00:00Z'
  ),
  (
    'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
    '22222222-2222-4222-8222-222222222222',
    'KAMAA-SECTION69-RESTORE-MARKER-001',
    'readback_probe',
    '2026-07-29T00:01:00Z'
  );

COMMIT;
