"""Communication Agent — Telegram messaging via Bot API (httpx, no heavy framework)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

from config import settings
from models import CommMessageRow

log = structlog.get_logger()

_TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
_OFFSET_STORE: dict[str, int] = {"offset": 0}


def _url(method: str) -> str:
    return _TELEGRAM_API.format(token=settings.telegram_bot_token, method=method)


# ─────────────────────────────────────────────────────────────────
# Outbound
# ─────────────────────────────────────────────────────────────────


async def send_telegram_message(chat_id: str, text: str) -> int | None:
    """Send a text message to a Telegram chat. Returns telegram message_id or None."""
    if not settings.telegram_bot_token:
        log.warning("telegram_token_not_set", chat_id=chat_id)
        return None

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            _url("sendMessage"),
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        )
        data = resp.json()

    if not data.get("ok"):
        log.error("telegram_send_error", chat_id=chat_id, error=data.get("description"))
        return None

    msg_id = data["result"]["message_id"]
    log.info("telegram_message_sent", chat_id=chat_id, message_id=msg_id)
    return msg_id


async def notify_roman(text: str) -> int | None:
    """Convenience: send message to Roman's personal chat."""
    if not settings.telegram_roman_chat_id:
        log.warning("telegram_roman_chat_id_not_set")
        return None
    return await send_telegram_message(settings.telegram_roman_chat_id, text)


# ─────────────────────────────────────────────────────────────────
# Inbound — long-poll getUpdates
# ─────────────────────────────────────────────────────────────────


async def poll_updates(timeout: int = 30) -> list[CommMessageRow]:
    """Long-poll Telegram getUpdates and return CommMessageRow objects."""
    if not settings.telegram_bot_token:
        return []

    rows: list[CommMessageRow] = []
    params: dict[str, Any] = {
        "timeout": timeout,
        "offset": _OFFSET_STORE["offset"],
        "allowed_updates": ["message"],
    }

    try:
        async with httpx.AsyncClient(timeout=timeout + 5) as client:
            resp = await client.get(_url("getUpdates"), params=params)
            data = resp.json()
    except httpx.ReadTimeout:
        return rows
    except Exception as exc:
        log.error("telegram_poll_error", error=str(exc))
        return rows

    if not data.get("ok"):
        log.warning("telegram_updates_not_ok", error=data.get("description"))
        return rows

    for update in data.get("result", []):
        _OFFSET_STORE["offset"] = update["update_id"] + 1
        msg = update.get("message")
        if not msg:
            continue

        chat_id = str(msg["chat"]["id"])
        from_user = msg.get("from", {})
        sender_name = from_user.get("username") or from_user.get("first_name", "unknown")
        text = msg.get("text", "")
        tg_msg_id = str(msg["message_id"])
        received = datetime.fromtimestamp(msg["date"], tz=timezone.utc)

        rows.append(
            CommMessageRow(
                channel="telegram",
                direction="inbound",
                external_id=tg_msg_id,
                sender=f"{sender_name}@telegram:{chat_id}",
                recipient=f"bot:{settings.telegram_bot_token[:6]}...",
                subject=None,
                body=text,
                metadata={
                    "chat_id": chat_id,
                    "from_user_id": str(from_user.get("id", "")),
                    "from_username": sender_name,
                    "update_id": update["update_id"],
                },
                status="read",
                received_at=received,
            )
        )

    if rows:
        log.info("telegram_updates_received", count=len(rows))

    return rows
