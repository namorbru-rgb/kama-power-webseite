# kama-power.ch Landingpage

Next.js 14 Landingpage für KAMA GmbH — statisch exportierbar, Hostinger-ready.

## Sektionen

1. **Hero** — Headline, Sub-Headline, CTA
2. **Leistungen** — 3 Kacheln: PV/Solar, BESS, LEG
3. **Referenzprojekte** — 3 Beispielprojekte
4. **Kontaktformular** — Webhook-Integration
5. **Footer** — Logo, Adresse, Links

## Lokale Entwicklung

```bash
cd apps/landingpage
cp .env.example .env.local
# .env.local anpassen (NEXT_PUBLIC_WEBHOOK_URL setzen)
npm install
npm run dev
# → http://localhost:3001
```

## Umgebungsvariablen

| Variable | Pflicht | Beschreibung |
|---|---|---|
| `NEXT_PUBLIC_WEBHOOK_URL` | Ja (Produktion) | KAMA-net Webhook-URL für Lead-Eingang |

## Build & Export (statisch)

```bash
npm run build
# Ausgabe: apps/landingpage/out/
```

Der `out/`-Ordner enthält alle statischen Dateien und kann direkt auf Hostinger hochgeladen werden.

## Deployment auf Hostinger (Static)

1. `npm run build` ausführen
2. Inhalt von `apps/landingpage/out/` per FTP/SFTP in den Hostinger-Webroot hochladen (z.B. `/public_html/`)
3. `.htaccess` für SPA-Routing hinzufügen (optional, da statisch exportiert):
   ```
   Options -MultiViews
   RewriteEngine On
   RewriteCond %{REQUEST_FILENAME} !-f
   RewriteRule ^ index.html [QSA,L]
   ```
4. Umgebungsvariable `NEXT_PUBLIC_WEBHOOK_URL` vor dem Build in `.env.local` setzen

## Deployment auf Hostinger (Node/Next.js)

1. Node.js-Hosting-Plan auf Hostinger wählen
2. Repo deployen, `npm install && npm run build && npm start`
3. Port: 3001 (oder Hostinger-Standard)
4. `NEXT_PUBLIC_WEBHOOK_URL` als Umgebungsvariable im Hostinger-Panel setzen

## Technischer Stack

- **Framework:** Next.js 14 (App Router)
- **Styling:** Tailwind CSS
- **Font:** Inter (Google Fonts)
- **Export:** statisch (`output: 'export'`)
- **Sprache:** TypeScript
