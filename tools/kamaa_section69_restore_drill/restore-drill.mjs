#!/usr/bin/env node
import { randomUUID } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '../..');
const fixturePath = join(__dirname, 'fixtures/section69-valid-snapshot.sql');
const artifactDir = join(repoRoot, 'artifacts/kamaa-1737');
const reportPath = join(artifactDir, 'section69-restore-drill-report.json');

const REQUIRED_HEADER = 'KAMAA_SECTION69_RESTORE_DRILL_SNAPSHOT_V1';
const REQUIRED_FIXTURE_ID = 'kamaa-section69-valid-2026-07-29';
const REQUIRED_SCHEMA_VERSION = '1';
const REQUIRED_MARKER = 'KAMAA-SECTION69-RESTORE-MARKER-001';

function run(command, args, options = {}) {
  const startedAt = new Date().toISOString();
  const result = spawnSync(command, args, {
    cwd: repoRoot,
    encoding: 'utf8',
    maxBuffer: 10 * 1024 * 1024,
    ...options,
  });
  return {
    command: [command, ...args].join(' '),
    exitCode: result.status,
    signal: result.signal,
    stdout: (result.stdout || '').trim(),
    stderr: (result.stderr || '').trim(),
    error: result.error ? result.error.message : null,
    startedAt,
    finishedAt: new Date().toISOString(),
  };
}

function fail(code, detail = {}) {
  return { ok: false, code, ...detail };
}

function pass(detail = {}) {
  return { ok: true, ...detail };
}

function readGit(commandArgs) {
  const result = run('git', commandArgs);
  return result.exitCode === 0 ? result.stdout : null;
}

function validateSnapshotText(label, sqlText) {
  const errors = [];
  const headerMatch = sqlText.includes(REQUIRED_HEADER);
  const fixtureMatch = new RegExp(`fixture_id:\\s*${REQUIRED_FIXTURE_ID}`).test(sqlText);
  const schemaMatch = new RegExp(`schema_version:\\s*${REQUIRED_SCHEMA_VERSION}`).test(sqlText);
  const markerMatch = new RegExp(`expected_marker:\\s*${REQUIRED_MARKER}`).test(sqlText);
  const destructiveMatch = /\b(DROP\s+DATABASE|CREATE\s+DATABASE|ALTER\s+SYSTEM|COPY\s+.+\s+PROGRAM)\b/i.test(sqlText);

  if (!headerMatch) errors.push('missing_required_snapshot_header');
  if (!fixtureMatch) errors.push('missing_or_wrong_fixture_id');
  if (!schemaMatch) errors.push('missing_or_incompatible_schema_version');
  if (!markerMatch) errors.push('missing_expected_data_marker');
  if (destructiveMatch) errors.push('disallowed_destructive_statement');

  return errors.length ? fail('snapshot_contract_rejected', { label, errors }) : pass({ label });
}

function validateSnapshotFile(path) {
  if (!existsSync(path)) {
    return fail('snapshot_input_missing', { path });
  }
  return validateSnapshotText(path, readFileSync(path, 'utf8'));
}

function runNegativeCases(validSql) {
  const cases = [
    {
      name: 'missing-input',
      result: validateSnapshotFile(join(__dirname, 'fixtures/does-not-exist.sql')),
      expectedCode: 'snapshot_input_missing',
    },
    {
      name: 'corrupted-input',
      result: validateSnapshotText('inline-corrupted', validSql.replace(REQUIRED_HEADER, 'BROKEN_HEADER')),
      expectedCode: 'snapshot_contract_rejected',
    },
    {
      name: 'incompatible-schema-version',
      result: validateSnapshotText('inline-incompatible', validSql.replace('schema_version: 1', 'schema_version: 2')),
      expectedCode: 'snapshot_contract_rejected',
    },
  ];

  return cases.map((entry) => ({
    ...entry,
    failClosed: entry.result.ok === false && entry.result.code === entry.expectedCode,
  }));
}

function dockerAvailable() {
  const version = run('docker', ['--version']);
  if (version.exitCode !== 0) return fail('docker_cli_unavailable', { probe: version });
  const info = run('docker', ['info', '--format', '{{.ServerVersion}}']);
  if (info.exitCode !== 0) return fail('docker_daemon_unavailable', { probe: info });
  return pass({ dockerVersion: version.stdout, dockerServerVersion: info.stdout });
}

function runPostgresDrill() {
  const containerName = `kamaa-section69-restore-${randomUUID()}`;
  const password = `section69-${randomUUID()}`;
  const cleanup = [];

  const start = run('docker', [
    'run',
    '--rm',
    '-d',
    '--name',
    containerName,
    '-e',
    `POSTGRES_PASSWORD=${password}`,
    '-e',
    'POSTGRES_USER=kamaa_restore',
    '-e',
    'POSTGRES_DB=kamaa_restore_drill',
    'postgres:16-alpine',
  ]);
  cleanup.push(() => run('docker', ['rm', '-f', containerName]));
  if (start.exitCode !== 0) {
    cleanup.forEach((fn) => fn());
    if (/Cannot connect to the Docker daemon|docker daemon|permission denied/i.test(start.stderr)) {
      return fail('runtime_gate', {
        runtimeGate: fail('docker_daemon_unavailable_at_container_start', { probe: start }),
      });
    }
    return fail('postgres_container_start_failed', { start });
  }

  const probes = [];
  let ready = false;
  for (let attempt = 1; attempt <= 30; attempt += 1) {
    const probe = run('docker', ['exec', containerName, 'pg_isready', '-U', 'kamaa_restore', '-d', 'kamaa_restore_drill']);
    probes.push({ attempt, exitCode: probe.exitCode, stdout: probe.stdout, stderr: probe.stderr });
    if (probe.exitCode === 0) {
      ready = true;
      break;
    }
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 1000);
  }

  if (!ready) {
    cleanup.forEach((fn) => fn());
    return fail('postgres_container_not_ready', { probes });
  }

  const copy = run('docker', ['cp', fixturePath, `${containerName}:/tmp/section69-valid-snapshot.sql`]);
  if (copy.exitCode !== 0) {
    cleanup.forEach((fn) => fn());
    return fail('snapshot_copy_failed', { copy });
  }

  const restore = run('docker', [
    'exec',
    '-e',
    `PGPASSWORD=${password}`,
    containerName,
    'psql',
    '-v',
    'ON_ERROR_STOP=1',
    '-U',
    'kamaa_restore',
    '-d',
    'kamaa_restore_drill',
    '-f',
    '/tmp/section69-valid-snapshot.sql',
  ]);
  if (restore.exitCode !== 0) {
    cleanup.forEach((fn) => fn());
    return fail('snapshot_restore_failed', { restore });
  }

  const readbackSql = `
WITH manifest AS (
  SELECT fixture_id, schema_version, expected_marker FROM restore_drill_manifest
),
counts AS (
  SELECT
    (SELECT count(*)::int FROM restore_drill_sites) AS site_count,
    (SELECT count(*)::int FROM restore_drill_events) AS event_count,
    (SELECT count(*)::int FROM restore_drill_events WHERE marker = '${REQUIRED_MARKER}') AS marker_count,
    (SELECT count(*)::int FROM restore_drill_events e LEFT JOIN restore_drill_sites s ON s.id = e.site_id WHERE s.id IS NULL) AS orphan_event_count
)
SELECT json_build_object(
  'fixtureId', manifest.fixture_id,
  'schemaVersion', manifest.schema_version,
  'expectedMarker', manifest.expected_marker,
  'siteCount', counts.site_count,
  'eventCount', counts.event_count,
  'markerCount', counts.marker_count,
  'orphanEventCount', counts.orphan_event_count
)::text
FROM manifest CROSS JOIN counts;
`;

  const readback = run('docker', [
    'exec',
    '-e',
    `PGPASSWORD=${password}`,
    containerName,
    'psql',
    '-v',
    'ON_ERROR_STOP=1',
    '-U',
    'kamaa_restore',
    '-d',
    'kamaa_restore_drill',
    '-tA',
    '-c',
    readbackSql,
  ]);

  cleanup.forEach((fn) => fn());

  if (readback.exitCode !== 0) {
    return fail('readback_query_failed', { restore, readback });
  }

  let invariants;
  try {
    invariants = JSON.parse(readback.stdout);
  } catch (error) {
    return fail('readback_json_parse_failed', { restore, readback, error: error.message });
  }

  const invariantErrors = [];
  if (invariants.fixtureId !== REQUIRED_FIXTURE_ID) invariantErrors.push('fixture_id_mismatch');
  if (invariants.schemaVersion !== 1) invariantErrors.push('schema_version_mismatch');
  if (invariants.expectedMarker !== REQUIRED_MARKER) invariantErrors.push('expected_marker_mismatch');
  if (invariants.siteCount !== 2) invariantErrors.push('site_count_mismatch');
  if (invariants.eventCount !== 2) invariantErrors.push('event_count_mismatch');
  if (invariants.markerCount !== 2) invariantErrors.push('marker_count_mismatch');
  if (invariants.orphanEventCount !== 0) invariantErrors.push('orphan_event_count_nonzero');

  if (invariantErrors.length) {
    return fail('readback_invariants_failed', { restore, readback, invariants, invariantErrors });
  }

  return pass({ restore, readback, invariants });
}

function main() {
  mkdirSync(artifactDir, { recursive: true });

  const baseSha = readGit(['rev-parse', 'origin/main']);
  const headSha = readGit(['rev-parse', 'HEAD']);
  const branch = readGit(['branch', '--show-current']);
  const dirtyStatus = readGit(['status', '--short']);
  const validSql = existsSync(fixturePath) ? readFileSync(fixturePath, 'utf8') : '';

  const snapshotContract = validateSnapshotFile(fixturePath);
  const negativeCases = runNegativeCases(validSql);
  const negativeFailClosed = negativeCases.every((entry) => entry.failClosed);
  const dockerProbe = dockerAvailable();

  let positiveDrill;
  if (!snapshotContract.ok) {
    positiveDrill = fail('valid_snapshot_contract_failed_before_restore', { snapshotContract });
  } else if (!dockerProbe.ok) {
    positiveDrill = fail('runtime_gate', { runtimeGate: dockerProbe });
  } else {
    positiveDrill = runPostgresDrill();
  }

  const status = positiveDrill.ok && negativeFailClosed ? 'pass' : positiveDrill.code === 'runtime_gate' ? 'runtime_gate' : 'fail';
  const report = {
    reportId: 'kamaa-1737-section69-restore-drill',
    generatedAt: new Date().toISOString(),
    status,
    repository: {
      branch,
      baseSha,
      headSha,
      dirtyStatus,
    },
    scope: {
      productionMutation: false,
      persistentVolume: false,
      secretsRequired: false,
      dockerImage: 'postgres:16-alpine',
      fixture: 'tools/kamaa_section69_restore_drill/fixtures/section69-valid-snapshot.sql',
    },
    snapshotContract,
    positiveDrill,
    negativeCases,
    summary: {
      positiveDrillPassed: positiveDrill.ok,
      negativeFailClosedCount: negativeCases.filter((entry) => entry.failClosed).length,
      negativeCaseCount: negativeCases.length,
    },
  };

  writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`);
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);

  if (status !== 'pass') {
    process.exitCode = status === 'runtime_gate' ? 2 : 1;
  }
}

main();
