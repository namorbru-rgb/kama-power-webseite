# Supabase Read-Only Integration

KAMA-net Supabase data is available via the Energy API under the `/kama-net/*` prefix.  
All routes are **read-only** (GET only). The **anon key** is used — the service-role key is never used here.

## Required Environment Variables

| Variable | Description | Default |
|---|---|---|
| `SUPABASE_URL` | Supabase project URL | `https://nixakeaiibzhesdwtelw.supabase.co` |
| `SUPABASE_ANON_KEY` | Supabase anon (public) key | _(empty — must be set)_ |
| `SUPABASE_TIMEOUT_SEC` | HTTP read timeout in seconds | `10.0` |

> **Security note:** Never set `SUPABASE_SERVICE_KEY` in the API service.  
> Read-only paths use only `SUPABASE_ANON_KEY`. See [KAMA-160](/KAMA/issues/KAMA-160) for key-rotation policy.

### `.env.dev` example

```dotenv
SUPABASE_URL=https://nixakeaiibzhesdwtelw.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### `docker-compose.yml` snippet (api service)

```yaml
api:
  environment:
    SUPABASE_URL: ${SUPABASE_URL:-https://nixakeaiibzhesdwtelw.supabase.co}
    SUPABASE_ANON_KEY: ${SUPABASE_ANON_KEY:-}
```

---

## Available Endpoints

### `GET /kama-net/customers`

List KAMA-net customers.

**Query params:**

| Param | Type | Default | Description |
|---|---|---|---|
| `limit` | int | 50 | Max rows (1–500) |
| `offset` | int | 0 | Pagination offset |
| `status` | string | — | Filter by status, e.g. `active` |

**Example:**

```bash
curl http://localhost:8000/kama-net/customers?limit=10&status=active
```

```json
{
  "total_returned": 3,
  "offset": 0,
  "items": [
    { "id": "...", "name": "Musterfarm AG", "status": "active", ... }
  ]
}
```

---

### `GET /kama-net/projects`

List KAMA-net projects.

**Query params:** `limit`, `offset`, `status`

```bash
curl http://localhost:8000/kama-net/projects?status=active
```

---

### `GET /kama-net/projects/{project_id}/documents`

List FM documents for a specific project.

**Query params:** `limit`, `offset`

```bash
curl http://localhost:8000/kama-net/projects/proj-abc-123/documents
```

---

### `GET /kama-net/solar-bss`

List solar BSS (battery storage system) assets.

**Query params:** `limit`, `offset`, `customer_id`

```bash
curl http://localhost:8000/kama-net/solar-bss?customer_id=cust-xyz
```

---

### `GET /kama-net/dashboard-summary`

Aggregate row counts from all four tables — used by the energy dashboard to show KAMA-net data availability.

```bash
curl http://localhost:8000/kama-net/dashboard-summary
```

```json
{
  "customer_count": 12,
  "project_count": 7,
  "solar_bss_count": 5,
  "document_count": 34
}
```

---

## Tables Read

| Table | Description |
|---|---|
| `app_customers` | Customer master data |
| `app_projects` | Solar/BESS project records |
| `app_fm_documents` | Facility management documents |
| `app_solar_bss` | Solar + battery storage system assets |

---

## Error Handling

| HTTP status | Cause |
|---|---|
| `503` | `SUPABASE_ANON_KEY` not set |
| `502` | Supabase returned a non-2xx response |
| `400` | Invalid query parameters (FastAPI validation) |

---

## Running Tests

```bash
cd apps/api
pip install pytest pytest-asyncio httpx
pytest tests/test_supabase_views.py -v
```
