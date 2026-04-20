"""Offer builder — generates German-language solar/BESS offer email."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from config import settings
from models import LeadInboundEvent, SolarCalcResult


def build_offer_markdown(lead: LeadInboundEvent, calc: SolarCalcResult) -> str:
    """Return a Markdown offer document (stored in DB and sent as email body)."""
    today = date.today()
    expiry = today + timedelta(days=settings.quote_validity_days)

    project_label = _project_label(lead.project_type)

    lines = [
        f"# Angebot {project_label} — {lead.customer_name}",
        "",
        f"**Datum:** {today.strftime('%d.%m.%Y')}  ",
        f"**Gültig bis:** {expiry.strftime('%d.%m.%Y')}  ",
        f"**Kontakt:** puk@kama-power.com  ",
        "",
        "---",
        "",
        "## Ihre Anlage im Überblick",
        "",
        f"| Parameter | Wert |",
        f"|-----------|------|",
        f"| Anlagenleistung | **{calc.system_size_kwp:.1f} kWp** |",
        f"| Jahresertrag (geschätzt) | **{calc.annual_yield_kwh:,.0f} kWh** |",
        f"| CO₂-Einsparung/Jahr | **{calc.co2_savings_kg_per_year / 1000:.1f} t CO₂** |",
        f"| Amortisationszeit | **ca. {calc.payback_years:.0f} Jahre** |",
        "",
        "## Investition",
        "",
        f"**Gesamtpreis (inkl. Montage, exkl. MwSt.):**  ",
        f"## CHF {calc.quote_value_chf:,.0f}.–",
        "",
        "> *Hinweis: Eventuelle Förderbeiträge (EIV, kantonale Programme) werden",
        "> nach Projektabschluss separat berechnet und können den Nettopreis",
        "> deutlich reduzieren.*",
        "",
        "---",
        "",
        "## Nächste Schritte",
        "",
        "1. Auftragsbestätigung per E-Mail oder Telefon",
        "2. Besichtigung und Detailplanung vor Ort",
        "3. Materialbeschaffung & Terminierung Montage",
        "4. Installation & Inbetriebnahme",
        "5. Netzanmeldung und Meldung an Pronovo",
        "",
        "---",
        "",
        "Bei Fragen stehe ich Ihnen jederzeit zur Verfügung.",
        "",
        "Freundliche Grüsse  ",
        "**KAMA GmbH — PUK**  ",
        "puk@kama-power.com",
    ]

    if lead.municipality:
        lines.insert(3, f"**Standort:** {lead.municipality}  ")

    return "\n".join(lines)


def build_offer_email(lead: LeadInboundEvent, calc: SolarCalcResult) -> tuple[str, str]:
    """Return (subject, plain-text email body) for the offer email."""
    project_label = _project_label(lead.project_type)
    expiry = date.today() + timedelta(days=settings.quote_validity_days)

    subject = (
        f"Ihr {project_label}-Angebot von KAMA — "
        f"{calc.system_size_kwp:.1f} kWp / CHF {calc.quote_value_chf:,.0f}.–"
    )

    body_lines = [
        f"Guten Tag {lead.customer_name}",
        "",
        f"Vielen Dank für Ihr Interesse an einer {project_label}-Anlage.",
        "Gerne unterbreiten wir Ihnen folgendes unverbindliches Angebot:",
        "",
        f"  Anlagenleistung:    {calc.system_size_kwp:.1f} kWp",
        f"  Jahresertrag:       {calc.annual_yield_kwh:,.0f} kWh (geschätzt)",
        f"  CO₂-Einsparung:     {calc.co2_savings_kg_per_year / 1000:.1f} t/Jahr",
        f"  Investition:        CHF {calc.quote_value_chf:,.0f}.– (exkl. MwSt.)",
        f"  Amortisation:       ca. {calc.payback_years:.0f} Jahre",
        f"  Gültig bis:         {expiry.strftime('%d.%m.%Y')}",
        "",
        "Mögliche Förderbeiträge (EIV, kantonale Programme) sind darin noch",
        "nicht berücksichtigt und können den Nettopreis deutlich reduzieren.",
        "",
        "Nächste Schritte:",
        "  1. Auftragsbestätigung per Antwort auf diese E-Mail",
        "  2. Besichtigung und Detailplanung vor Ort",
        "  3. Installation & Inbetriebnahme",
        "",
        "Bei Fragen stehe ich Ihnen jederzeit zur Verfügung.",
        "",
        "Freundliche Grüsse",
        "KAMA GmbH — PUK",
        "puk@kama-power.com",
    ]

    return subject, "\n".join(body_lines)


def build_followup_email(
    customer_name: str,
    project_type: str,
    system_size_kwp: float | None,
    quote_value_chf: float | None,
    attempt: int = 1,
) -> tuple[str, str]:
    """Return (subject, plain-text body) for a follow-up email."""
    project_label = _project_label(project_type)
    size_str = f"{system_size_kwp:.1f} kWp / " if system_size_kwp else ""
    value_str = f"CHF {quote_value_chf:,.0f}.–" if quote_value_chf else "gemäss Angebot"

    subject = f"Nachfrage: Ihr {project_label}-Angebot von KAMA ({size_str}{value_str})"

    if attempt == 1:
        intro = (
            "vor einer Woche haben wir Ihnen unser Angebot für eine "
            f"{project_label}-Anlage zugesandt."
        )
    else:
        intro = (
            f"wir wollten kurz nachfragen, ob Sie unser {project_label}-Angebot "
            "erhalten haben und ob noch Fragen offen sind."
        )

    body_lines = [
        f"Guten Tag {customer_name}",
        "",
        f"Gerne erinnern wir Sie: {intro}",
        "",
        "Haben Sie das Angebot erhalten? Haben Sie Fragen oder wünschen Sie",
        "einen Besichtigungstermin vor Ort?",
        "",
        "Wir freuen uns auf Ihre Rückmeldung.",
        "",
        "Freundliche Grüsse",
        "KAMA GmbH — PUK",
        "puk@kama-power.com",
    ]

    return subject, "\n".join(body_lines)


def _project_label(project_type: str) -> str:
    return {
        "solar": "Solar",
        "bess": "Batteriespeicher",
        "vzev": "VZEV",
        "combined": "Solar+Speicher",
    }.get(project_type, "Solar")


def quote_expires_at() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=settings.quote_validity_days)
