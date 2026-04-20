"""Mailer — sends procurement emails via SMTP (himalaya-compatible).

One email per supplier per order. Returns the SMTP Message-ID for thread tracking.
"""
from __future__ import annotations

import email.utils
import smtplib
import uuid
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import structlog

from config import settings
from models import DeltaItem

log = structlog.get_logger()

# Supplier contact registry (from KAMA-29 spec)
SUPPLIER_CONTACTS: dict[str, dict[str, str]] = {
    "andercore": {
        "name": "Max Distler",
        "email": "bestellen@andercore.ch",
        "lead_days": "3",
        "customer_note": "",
    },
    "tritec": {
        "name": "Patrick Ackermann",
        "email": "bestellung@tritec.ch",
        "lead_days": "10",
        "customer_note": "Kundennummer 21048202 — 15% Rabatt beachten",
    },
    "mph": {
        "name": "Patrick Hanisch",
        "email": "info@mph-solar.ch",
        "lead_days": "7",
        "customer_note": "",
    },
    "solarmarkt": {
        "name": "Solarmarkt.ch Portal",
        "email": "bestellung@solarmarkt.ch",
        "lead_days": "5",
        "customer_note": "Portal-Login: roman.bruderer@my-strom.ch",
    },
}


def send_order_email(
    auftrag_id: str,
    supplier: str,
    items: list[DeltaItem],
    customer_name: str = "",
) -> tuple[str, date]:
    """Send a supplier order email and return (message_id, expected_delivery_date)."""
    contact = SUPPLIER_CONTACTS.get(supplier, SUPPLIER_CONTACTS["solarmarkt"])
    today = date.today()
    lead_days = int(contact["lead_days"])
    expected_delivery = today + timedelta(days=lead_days)

    msg = _build_email(auftrag_id, supplier, items, customer_name, contact, expected_delivery)

    message_id = msg["Message-ID"]

    if settings.debug:
        log.info(
            "mailer_debug_mode",
            to=contact["email"],
            subject=msg["Subject"],
            items=len(items),
        )
        return message_id, expected_delivery

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_from, [contact["email"]], msg.as_string())
        log.info(
            "order_email_sent",
            auftrag_id=auftrag_id,
            supplier=supplier,
            to=contact["email"],
            message_id=message_id,
            expected_delivery=str(expected_delivery),
        )
    except Exception as exc:
        log.error("mailer_error", supplier=supplier, error=str(exc))
        raise

    return message_id, expected_delivery


def _build_email(
    auftrag_id: str,
    supplier: str,
    items: list[DeltaItem],
    customer_name: str,
    contact: dict[str, str],
    expected_delivery: date,
) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["From"] = settings.smtp_from
    msg["To"] = contact["email"]
    msg["Subject"] = f"Bestellung — {auftrag_id} — {date.today().isoformat()}"
    msg["Message-ID"] = email.utils.make_msgid(domain="kama-power.com")

    # Build article table
    table_lines = ["| Artikel | Menge | Einheit | EK-Preis (CHF) |"]
    table_lines.append("|---------|-------|---------|----------------|")
    for item in items:
        price = f"{item.ek_price_chf:.2f}" if item.ek_price_chf else "—"
        table_lines.append(
            f"| {item.article_name} | {item.qty_to_order} | {item.unit} | {price} |"
        )
    table = "\n".join(table_lines)

    note = f"\n\nHinweis: {contact['customer_note']}" if contact["customer_note"] else ""
    project_info = f" (Projekt: {customer_name})" if customer_name else ""

    body = f"""Sehr geehrte/r {contact['name']},

hiermit bestellen wir folgende Materialien für Auftrag {auftrag_id}{project_info}:

{table}

Gewünschter Liefertermin: {expected_delivery.isoformat()}

Bitte bestätigen Sie Liefertermin und Verfügbarkeit per Rückantwort auf diese E-Mail.{note}

Mit freundlichen Grüssen
KAMA GmbH
puk@kama-power.com
"""
    msg.attach(MIMEText(body, "plain", "utf-8"))
    return msg


def send_overdue_alert(auftrag_id: str, supplier: str, expected_delivery: date) -> None:
    """Notify internal team about an overdue delivery (internal alert email)."""
    msg = MIMEMultipart()
    msg["From"] = settings.smtp_from
    msg["To"] = settings.smtp_from  # internal loop-back
    msg["Subject"] = f"ALERT: Lieferverzug — {auftrag_id} / {supplier}"
    msg["Message-ID"] = email.utils.make_msgid(domain="kama-power.com")

    body = (
        f"Lieferverzug erkannt!\n\n"
        f"Auftrag:    {auftrag_id}\n"
        f"Lieferant:  {supplier}\n"
        f"Erwartet:   {expected_delivery.isoformat()}\n"
        f"Heute:      {date.today().isoformat()}\n\n"
        f"Bitte Lieferanten kontaktieren und Lager-Agent informieren."
    )
    msg.attach(MIMEText(body, "plain", "utf-8"))

    if settings.debug:
        log.info("overdue_alert_debug", auftrag_id=auftrag_id, supplier=supplier)
        return

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_from, [settings.smtp_from], msg.as_string())
        log.info("overdue_alert_sent", auftrag_id=auftrag_id, supplier=supplier)
    except Exception as exc:
        log.error("overdue_alert_error", error=str(exc))
