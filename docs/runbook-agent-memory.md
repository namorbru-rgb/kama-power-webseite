# Runbook: Supabase Agent Memory

## ENV-Variablen

| Variable                     | Pflicht | Beschreibung |
|------------------------------|---------|--------------|
| `SUPABASE_SERVICE_ROLE_KEY`  | Ja      | Supabase Service Role Secret (niemals im Frontend exponieren). Im Supabase Dashboard unter **Project Settings → API**. |
| `SUPABASE_URL`               | Nein    | Supabase Projekt-URL. Standardmaessig wird `KAMA_NET_URL` verwendet (`https://nixakeaiibzhesdwtelw.supabase.co`). |
| `AGENT_MEMORY_ENABLED`       | Nein    | `true` aktiviert Read/Write-Hooks (Standard: `false` — Shadow-Write-Phase). |
| `AGENT_MEMORY_SCOPE`         | Nein    | Scope-Label fuer Memory-Items (Standard: `project-workflow-engine`). |
| `AGENT_MEMORY_AGENT_ID`      | Nein    | Logische Agent-ID in den Memory-Tabellen (Standard: `kama-project-workflow-engine`). |
| `AGENT_MEMORY_READ_LIMIT`    | Nein    | Max. Memory-Items beim Start (Standard: `20`). |

Beispiel `.env`-Eintrag:
```
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
AGENT_MEMORY_ENABLED=true
```

## Rollout-Phasen

### Phase 1 — Shadow-Write (1-2 Tage)
- `AGENT_MEMORY_ENABLED=false` (Standard): Memory-Hooks werden nicht ausgefuehrt.
- Migration `db/migrations/011_agent_memory.sql` gegen Supabase ausfuehren (einmalig, idempotent).
- Tabellen pruefen: `agent_memory_items`, `agent_memory_events`, `agent_memory_snapshots`.

### Phase 2 — Aktivierung
- `AGENT_MEMORY_ENABLED=true` + `SUPABASE_SERVICE_ROLE_KEY` setzen.
- Service neu starten. Log-Events `agent_memory_context_loaded` + `agent_memory_item_written` pruefen.
- Tabellen-Inserts verifizieren: `SELECT count(*) FROM agent_memory_items;`

### Phase 3 — Erweiterung auf weitere Services
- `memory_store.py` in weitere Service-Verzeichnisse kopieren oder als shared lib extrahieren.
- Gleiche ENV-Variablen, unterschiedliche `AGENT_MEMORY_SCOPE` / `AGENT_MEMORY_AGENT_ID`.

## Migration ausfuehren

```bash
# Einmalig gegen Supabase Postgres (via psql oder Supabase SQL Editor)
psql "$SUPABASE_DB_URL" -f db/migrations/011_agent_memory.sql
```

Alternativ: Inhalt von `011_agent_memory.sql` direkt im **Supabase SQL Editor** ausfuehren.

## Smoke Test

```python
import asyncio
from memory_store import read_memory, write_memory_item

async def smoke():
    await write_memory_item(
        supabase_url="https://nixakeaiibzhesdwtelw.supabase.co",
        service_role_key="<SERVICE_ROLE_KEY>",
        agent_id="test-agent",
        kind="smoke_test",
        summary="Smoke test entry",
        scope="test",
    )
    items = await read_memory(
        supabase_url="https://nixakeaiibzhesdwtelw.supabase.co",
        service_role_key="<SERVICE_ROLE_KEY>",
        agent_id="test-agent",
        scope="test",
    )
    assert len(items) >= 1, "Expected at least 1 memory item"
    print("Smoke test passed:", items[0]["summary"])

asyncio.run(smoke())
```

## Monitoring

- Log-Events: `agent_memory_context_loaded`, `agent_memory_item_written`, `agent_memory_snapshot_written`
- Fehlerfaelle: `agent_memory_read_failed`, `agent_memory_write_failed` (Service laeuft weiter)
- Supabase Dashboard → Table Editor → `agent_memory_items` fuer manuelle Inspektion
