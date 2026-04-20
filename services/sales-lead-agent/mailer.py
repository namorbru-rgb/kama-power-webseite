"""SMTP mailer — sends emails via puk@kama-power.com."""
from __future__ import annotations

import email.utils
import smtplib
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import structlog

from config import settings

log = structlog.get_logger()


def send_email(
    to: str,
    subject: str,
    body: str,
    in_reply_to: str | None = None,
) -> str | None:
    """Send a plain-text email and return the Message-ID on success."""
    if not settings.smtp_password:
        log.warning("smtp_not_configured", to=to, subject=subject)
        return None

    message_id = f"<{uuid.uuid4()}@kama-power.com>"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Message-ID"] = message_id
    msg["Date"] = email.utils.formatdate(localtime=True)

    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to

    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.sendmail(settings.smtp_from, [to], msg.as_string())
        log.info("email_sent", to=to, subject=subject, message_id=message_id)
        return message_id
    except smtplib.SMTPException as exc:
        log.error("email_send_failed", to=to, error=str(exc))
        return None
