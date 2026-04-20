"""Communication Agent — SMTP sender and IMAP poller for puk@kama-power.com."""
from __future__ import annotations

import asyncio
import email
import email.policy
import imaplib
import smtplib
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Iterator

import structlog

from config import settings
from models import CommMessageRow

log = structlog.get_logger()


# ─────────────────────────────────────────────────────────────────
# Outbound — SMTP
# ─────────────────────────────────────────────────────────────────


def send_email(
    recipient: str,
    subject: str,
    body: str,
    in_reply_to: str | None = None,
    references: str | None = None,
) -> str:
    """Send an email via SMTP. Returns the Message-ID header value."""
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = recipient
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=True)

    message_id = f"<{uuid.uuid4()}@kama-power.com>"
    msg["Message-ID"] = message_id

    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = f"{references} {in_reply_to}".strip() if references else in_reply_to

    msg.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)

    log.info(
        "email_sent",
        recipient=recipient,
        subject=subject,
        message_id=message_id,
    )
    return message_id


# ─────────────────────────────────────────────────────────────────
# Inbound — IMAP polling
# ─────────────────────────────────────────────────────────────────


def _fetch_unseen(imap: imaplib.IMAP4_SSL) -> Iterator[email.message.Message]:
    """Yield unread messages from INBOX and mark them as SEEN."""
    imap.select("INBOX")
    _, data = imap.search(None, "UNSEEN")
    uid_list = data[0].split() if data[0] else []
    for uid in uid_list:
        _, msg_data = imap.fetch(uid, "(RFC822)")
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw, policy=email.policy.default)
        imap.store(uid, "+FLAGS", "\\Seen")
        yield msg


def _extract_body(msg: email.message.Message) -> str:
    """Return plain-text body, falling back to html stripped."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                return part.get_payload(decode=True).decode(errors="replace")
    payload = msg.get_payload(decode=True)
    if payload:
        return payload.decode(errors="replace")
    return ""


def poll_inbox() -> list[CommMessageRow]:
    """Connect via IMAP and return CommMessageRow objects for each unseen message."""
    rows: list[CommMessageRow] = []
    try:
        with imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port) as imap:
            imap.login(settings.imap_user, settings.imap_password)
            for msg in _fetch_unseen(imap):
                message_id = msg.get("Message-ID", "").strip()
                in_reply_to = msg.get("In-Reply-To", "").strip() or None
                sender = msg.get("From", "")
                subject = msg.get("Subject", "")
                body = _extract_body(msg)
                received = datetime.now(timezone.utc)

                rows.append(
                    CommMessageRow(
                        channel="email",
                        direction="inbound",
                        external_id=message_id or None,
                        sender=sender,
                        recipient=settings.imap_user,
                        subject=subject,
                        body=body,
                        metadata={
                            "in_reply_to": in_reply_to,
                            "raw_from": sender,
                        },
                        status="read",
                        received_at=received,
                    )
                )
    except Exception as exc:
        log.error("imap_poll_error", error=str(exc))
    return rows


# ─────────────────────────────────────────────────────────────────
# Async wrapper for polling (runs sync IMAP in executor)
# ─────────────────────────────────────────────────────────────────


async def async_poll_inbox() -> list[CommMessageRow]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, poll_inbox)


async def async_send_email(
    recipient: str,
    subject: str,
    body: str,
    in_reply_to: str | None = None,
    references: str | None = None,
) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, send_email, recipient, subject, body, in_reply_to, references
    )
