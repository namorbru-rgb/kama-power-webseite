# KAMAA Section 69 Ephemeral Restore Drill

This tool proves a non-production restore path against a disposable PostgreSQL
instance. It never uses project `.env` files, production hostnames, Supabase
service-role keys, or persistent Docker volumes.

Run:

```bash
npm run restore-drill:section69
```

The runner:

1. Validates the snapshot fixture contract before any database action.
2. Starts a throwaway `postgres:16-alpine` container with a random database
   password and no host port publishing.
3. Restores `fixtures/section69-valid-snapshot.sql`.
4. Reads back schema invariants and the expected marker.
5. Executes fail-closed negative cases for missing input, corrupted input, and
   incompatible schema version.
6. Writes a machine-readable report to
   `artifacts/kamaa-1737/section69-restore-drill-report.json`.

If Docker is unavailable, the report status is `runtime_gate` and records the
exact missing runtime. That state is not a PASS.
