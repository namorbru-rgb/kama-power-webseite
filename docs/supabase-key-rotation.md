# Supabase Key-Rotation & Secret-Hygiene

## Secret-Hygiene Policy

1. **Keine Secrets in Issue-Kommentaren.** API-Keys, Passwörter und Tokens dürfen niemals in Paperclip-Kommentaren, GitHub-Issues oder Pull-Requests stehen. Wer einen Key teilen muss, übergibt ihn über den sicheren Kanal (1Password / Vault) oder trägt ihn direkt in die Produktionsumgebung ein.

2. **Anon-Key = öffentlich lesbar.** `KAMA_NET_API_KEY` / `SUPABASE_ANON_KEY` ist der Postgres-Row-Level-Security-geschützte Leseschlüssel. Er darf in Browser-Apps und Server-APIs verwendet werden, aber nur für Leseoperationen auf explizit freigegebenen Tabellen (siehe `ALLOWED_TABLES` in `apps/api/supabase_client.py`).

3. **Service-Role-Key = serverseitig only.** `SUPABASE_SERVICE_ROLE_KEY` umgeht RLS. Nur `services/project-workflow-engine` (Agent-Memory) darf ihn verwenden. Niemals im Frontend, niemals in Logs, niemals in Issue-Kommentaren.

4. **`.env`-Dateien nicht committen.** Nur `.env.example` liegt im Repo. Produktions-Secrets werden über Docker-Compose-Variablen aus der Host-Umgebung injiziert.

## Key-Rotation Procedure

### Wann rotieren?
- Wenn ein Key versehentlich exponiert wurde (z. B. in einem Kommentar, Log-Output, etc.)
- Routinemäßig alle 90 Tage (empfohlen)

### Schritte

#### 1. Neuen Service-Role-Key generieren
```
Supabase Dashboard → Project Settings → API → Regenerate service_role secret
```
Den neuen Key sofort in den sicheren Passwortmanager (1Password/Vault) ablegen.

#### 2. Alt-Key invalidieren
Der neue Key ist nach dem Regenerieren sofort aktiv. Der alte Key ist damit ungültig.

#### 3. Neuen Key in Produktionsumgebung eintragen
Nur für den `project-workflow-engine`-Service:
```bash
# Auf dem Produktions-Host:
export SUPABASE_SERVICE_ROLE_KEY="<neuer-key>"
docker compose up -d project-workflow-engine
```

#### 4. Verifikationstest ausführen

```bash
# Anon-Key-Test (read-only path muss weiterhin funktionieren)
curl -s \
  -H "apikey: $KAMA_NET_API_KEY" \
  -H "Authorization: Bearer $KAMA_NET_API_KEY" \
  "$KAMA_NET_URL/rest/v1/app_customers?limit=1" \
  | grep -q '"id"' && echo "PASS: anon read OK" || echo "FAIL: anon read failed"

# Service-Role-Key-Test (agent memory muss mit neuem Key schreiben können)
curl -s -o /dev/null -w "%{http_code}" \
  -X GET \
  -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
  -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" \
  "$KAMA_NET_URL/rest/v1/agent_memory_items?limit=1"
# Erwartet: 200 (oder 400 falls Tabelle noch nicht existiert, aber nicht 401)

# Alter Key (sollte 401 zurückgeben — diesen Test nur bei bekanntem altem Key)
# curl -s -o /dev/null -w "%{http_code}" \
#   -H "apikey: <ALTER-KEY>" \
#   -H "Authorization: Bearer <ALTER-KEY>" \
#   "$KAMA_NET_URL/rest/v1/app_customers?limit=1"
# Erwartet: 401
```

#### 5. Anon-Key-Rotation (falls nötig)
Falls auch der Anon-Key rotiert werden muss:
```
Supabase Dashboard → Project Settings → API → Regenerate anon secret
```
Dann alle Services neu starten (alle Services nutzen `KAMA_NET_API_KEY`):
```bash
export KAMA_NET_API_KEY="<neuer-anon-key>"
export SUPABASE_ANON_KEY="<neuer-anon-key>"
docker compose up -d
```

## Betroffene Services und Keys

| Service | Key | Zweck |
|---------|-----|-------|
| `apps/api` | `SUPABASE_ANON_KEY` | Read-only REST via PostgREST |
| `services/sales-lead-agent` | `KAMA_NET_API_KEY` | Read/Write Inquiries/Orders |
| `services/project-workflow-engine` | `KAMA_NET_API_KEY` + `SUPABASE_SERVICE_ROLE_KEY` | Read + Agent-Memory Write |
| `services/procurement-agent` | `KAMA_NET_API_KEY` | Read Inventory |
| `services/montage-agent` | `KAMA_NET_API_KEY` | Read Projects |
| `services/lager-logistik-agent` | `KAMA_NET_API_KEY` | Read/Write Stock |
| `services/communication-agent` | `KAMA_NET_API_KEY` | Read Contacts |

## Read-Only Path Enforcement

`apps/api/supabase_client.py` erzwingt:
- Nur `ALLOWED_TABLES = {"app_fm_documents", "app_projects", "app_customers", "app_solar_bss"}` sind abfragbar
- Ausschließlich HTTP GET (keine POST/PATCH/DELETE)
- Authentifizierung nur über Anon-Key (kein Service-Role-Key in diesem Modul)

Tests: `apps/api/tests/test_supabase_views.py`
