"""
Weekly management report generator
===================================
Fetches the dashboard summary from the API and sends a formatted
HTML + plaintext email to the configured recipients.

Run modes:
  - Scheduled: invoked by cron (see main.py)
  - One-shot:  python report_generator.py  (for manual testing)
"""

import smtplib
import textwrap
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx
import structlog

from config import settings

log = structlog.get_logger()


# ── Data fetching ──────────────────────────────────────────────────────────────

async def fetch_summary() -> dict:
    async with httpx.AsyncClient(base_url=settings.api_base_url, timeout=30.0) as client:
        resp = await client.get("/dashboard/summary")
        resp.raise_for_status()
        return resp.json()


async def fetch_bess_detail() -> dict:
    async with httpx.AsyncClient(base_url=settings.api_base_url, timeout=30.0) as client:
        resp = await client.get("/dashboard/bess")
        resp.raise_for_status()
        return resp.json()


async def fetch_pipeline_detail() -> dict:
    async with httpx.AsyncClient(base_url=settings.api_base_url, timeout=30.0) as client:
        resp = await client.get("/dashboard/pipeline")
        resp.raise_for_status()
        return resp.json()


# ── Report rendering ───────────────────────────────────────────────────────────

def _temperature_emoji(temp: str) -> str:
    return {"hot": "🔴", "warm": "🟡", "cold": "🔵"}.get(temp, "⚪")


def render_html(summary: dict, bess: dict, pipeline: dict) -> str:
    af = summary["anfragen"]
    pl = summary["pipeline"]
    bs = summary["bess"]
    as_of = summary["as_of"][:10]

    # Pipeline status rows
    status_order = ["commissioning", "installation", "ordered", "planning"]
    status_de = {
        "commissioning": "IBN",
        "installation":  "Montage",
        "ordered":       "Bestellt",
        "planning":      "Planung",
    }
    pl_by_status = pl["by_status"]
    pipeline_rows = "".join(
        f"<tr><td>{status_de.get(s, s)}</td><td>{pl_by_status.get(s, 0)}</td></tr>"
        for s in status_order
        if pl_by_status.get(s, 0) > 0
    )

    # BESS open IBN
    open_ibn = [
        i for i in bess["installations"]
        if i["status"] == "commissioning" and i["ibn_planned_date"] and not i["ibn_actual_date"]
    ]
    ibn_rows = "".join(
        f"<tr><td>{i['name']}</td><td>{i['customer_name']}</td>"
        f"<td>{i['ibn_planned_date']}</td></tr>"
        for i in open_ibn
    )
    ibn_table = (
        f"""
        <h3>Offene IBN-Termine ({len(open_ibn)})</h3>
        <table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;">
          <tr><th>Anlage</th><th>Kunde</th><th>IBN geplant</th></tr>
          {ibn_rows}
        </table>
        """
        if open_ibn
        else "<p><em>Keine offenen IBN-Termine.</em></p>"
    )

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>KAMA Wochenbericht {as_of}</title></head>
<body style="font-family: Arial, sans-serif; max-width: 700px; margin: auto; color: #222;">

<h1 style="color:#1a6e3c;">KAMA Wochenbericht — {as_of}</h1>

<h2>Anfragen (AFs)</h2>
<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;">
  <tr><th>Gesamt offen</th><th>🔴 Hot</th><th>🟡 Warm</th><th>🔵 Kalt</th><th>Neu (7T)</th><th>Pipeline (CHF)</th></tr>
  <tr>
    <td style="text-align:center;">{af['total_open']}</td>
    <td style="text-align:center;">{af['hot']}</td>
    <td style="text-align:center;">{af['warm']}</td>
    <td style="text-align:center;">{af['cold']}</td>
    <td style="text-align:center;">{af['new_last_7d']}</td>
    <td style="text-align:right;">CHF {af['estimated_pipeline_chf']:,.0f}</td>
  </tr>
</table>
<p style="font-size:0.85em;color:#666;">
  Solar: {af['by_type'].get('solar', 0)} | BESS: {af['by_type'].get('bess', 0)} |
  VZEV: {af['by_type'].get('vzev', 0)} | Kombiniert: {af['by_type'].get('combined', 0)}
</p>

<h2>Auftragspipeline</h2>
<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;">
  <tr><th></th><th>Anzahl</th><th>Volumen (CHF)</th></tr>
  <tr><td>Solar</td><td>{pl['solar_count']}</td><td style="text-align:right;">CHF {pl['solar_value_chf']:,.0f}</td></tr>
  <tr><td>BESS</td><td>{pl['bess_count']}</td><td style="text-align:right;">CHF {pl['bess_value_chf']:,.0f}</td></tr>
  <tr style="font-weight:bold;"><td>Total aktiv</td><td>{pl['total_active']}</td><td style="text-align:right;">CHF {pl['total_value_chf']:,.0f}</td></tr>
</table>
<h3>Nach Status</h3>
<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;">
  <tr><th>Status</th><th>Aufträge</th></tr>
  {pipeline_rows}
</table>

<h2>BESS Feldbestand</h2>
<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;">
  <tr><th>Gesamt</th><th>Betrieb</th><th>IBN</th><th>Service</th><th>Offline</th><th>Kapazität (kWh)</th><th>Leistung (kW)</th></tr>
  <tr>
    <td style="text-align:center;">{bs['total']}</td>
    <td style="text-align:center;">{bs['operational']}</td>
    <td style="text-align:center;">{bs['commissioning']}</td>
    <td style="text-align:center;">{bs['maintenance']}</td>
    <td style="text-align:center;">{bs['offline']}</td>
    <td style="text-align:right;">{bs['total_capacity_kwh']:,.1f}</td>
    <td style="text-align:right;">{bs['total_power_kw']:,.1f}</td>
  </tr>
</table>

{ibn_table}

<hr>
<p style="font-size:0.8em;color:#999;">
  Generiert von KAMA Energy Platform — {as_of} |
  <a href="{settings.api_base_url}/dashboard/summary">Live Dashboard</a>
</p>

</body>
</html>"""


def render_plaintext(summary: dict) -> str:
    af = summary["anfragen"]
    pl = summary["pipeline"]
    bs = summary["bess"]
    as_of = summary["as_of"][:10]

    return textwrap.dedent(f"""\
        KAMA Wochenbericht — {as_of}
        ================================

        ANFRAGEN (AFs)
        --------------
        Gesamt offen : {af['total_open']}
        Hot          : {af['hot']}
        Warm         : {af['warm']}
        Kalt         : {af['cold']}
        Neu (7 Tage) : {af['new_last_7d']}
        Pipeline     : CHF {af['estimated_pipeline_chf']:,.0f}
        Solar/BESS/VZEV/Kombi: {af['by_type'].get('solar',0)}/{af['by_type'].get('bess',0)}/{af['by_type'].get('vzev',0)}/{af['by_type'].get('combined',0)}

        AUFTRAGSPIPELINE
        ----------------
        Total aktiv  : {pl['total_active']} | CHF {pl['total_value_chf']:,.0f}
        Solar        : {pl['solar_count']} | CHF {pl['solar_value_chf']:,.0f}
        BESS         : {pl['bess_count']} | CHF {pl['bess_value_chf']:,.0f}

        BESS FELDBESTAND
        ----------------
        Gesamt       : {bs['total']}
        Betrieb      : {bs['operational']}
        IBN          : {bs['commissioning']} (offene IBN-Termine: {bs['open_ibn_count']})
        Service      : {bs['maintenance']}
        Offline      : {bs['offline']}
        Kapazität    : {bs['total_capacity_kwh']:,.1f} kWh / {bs['total_power_kw']:,.1f} kW
    """)


# ── Email delivery ─────────────────────────────────────────────────────────────

def send_report(subject: str, html_body: str, text_body: str) -> None:
    recipients = [r.strip() for r in settings.report_recipients.split(",") if r.strip()]
    if not recipients:
        log.warning("No report recipients configured — skipping email delivery")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        smtp.ehlo()
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.sendmail(settings.smtp_from, recipients, msg.as_string())

    log.info("Weekly report sent", recipients=recipients, subject=subject)


# ── Entry point ────────────────────────────────────────────────────────────────

async def run_report() -> None:
    log.info("Starting weekly report generation")
    try:
        summary, bess, pipeline = await _gather_data()
    except Exception as exc:
        log.error("Failed to fetch dashboard data", error=str(exc))
        raise

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    subject = f"KAMA Wochenbericht {today}"
    html = render_html(summary, bess, pipeline)
    text = render_plaintext(summary)

    if settings.debug:
        log.info("Debug mode — printing report instead of sending email")
        print(text)
        return

    send_report(subject, html, text)
    log.info("Weekly report complete")


async def _gather_data():
    import asyncio
    summary, bess, pipeline = await asyncio.gather(
        fetch_summary(),
        fetch_bess_detail(),
        fetch_pipeline_detail(),
    )
    return summary, bess, pipeline
