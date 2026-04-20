"""Sales & Lead Agent — Kafka consumer + lead-to-order workflow."""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg
import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.errors import KafkaError
from pydantic import ValidationError

import kama_net_client
from config import settings
from db import (
    cancel_followups_for_quote,
    expire_overdue_quotes,
    get_due_followups,
    get_quote_by_anfrage,
    get_quote_by_email_message_id,
    insert_followup,
    insert_quote,
    mark_followup_sent,
    update_quote_status,
)
from lead_qualifier import qualify, solar_calc
from mailer import send_email
from models import (
    CommReplyReceivedEvent,
    CommSendRequest,
    LeadInboundEvent,
    OrderConfirmedEvent,
    SalesFollowupRow,
    SalesQuoteRow,
)
from offer_builder import (
    build_followup_email,
    build_offer_email,
    build_offer_markdown,
    quote_expires_at,
)

log = structlog.get_logger()


class SalesLeadAgent:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
        self._consumer: AIOKafkaConsumer | None = None
        self._producer: AIOKafkaProducer | None = None
        self._running = False

        self.total_received = 0
        self.total_processed = 0
        self.total_errors = 0

    # ─────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        topics = [
            settings.kafka_topic_leads_inbound,
            settings.kafka_topic_comm_reply,
        ]
        self._consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=settings.kafka_group_id,
            auto_offset_reset="earliest",
            enable_auto_commit=False,
        )
        self._producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, default=str).encode(),
        )
        await self._consumer.start()
        await self._producer.start()
        self._running = True
        log.info("sales_lead_agent_started", topics=topics, group=settings.kafka_group_id)

    async def stop(self) -> None:
        self._running = False
        if self._consumer:
            await self._consumer.stop()
        if self._producer:
            await self._producer.stop()
        log.info(
            "sales_lead_agent_stopped",
            received=self.total_received,
            processed=self.total_processed,
            errors=self.total_errors,
        )

    async def run(self) -> None:
        """Main event loop: consume Kafka + periodic follow-up checks."""
        assert self._consumer is not None

        # Background task: check due follow-ups every N seconds
        followup_task = asyncio.create_task(self._followup_loop())

        try:
            async for msg in self._consumer:
                await self._handle(msg)
                await self._consumer.commit()
        except asyncio.CancelledError:
            pass
        except KafkaError as exc:
            log.error("kafka_error", exc=str(exc))
            raise
        finally:
            followup_task.cancel()
            try:
                await followup_task
            except asyncio.CancelledError:
                pass

    # ─────────────────────────────────────────────────────────────
    # Dispatch
    # ─────────────────────────────────────────────────────────────

    async def _handle(self, msg: Any) -> None:
        self.total_received += 1
        try:
            payload = json.loads(msg.value)
        except json.JSONDecodeError as exc:
            self.total_errors += 1
            log.warning("invalid_json", topic=msg.topic, error=str(exc))
            return

        try:
            if msg.topic == settings.kafka_topic_leads_inbound:
                await self._handle_lead_inbound(payload)
            elif msg.topic == settings.kafka_topic_comm_reply:
                await self._handle_reply(payload)
            else:
                log.debug("unknown_topic", topic=msg.topic)
            self.total_processed += 1
        except Exception as exc:
            self.total_errors += 1
            log.error(
                "event_handling_error",
                topic=msg.topic,
                error=str(exc),
                exc_info=True,
            )

    # ─────────────────────────────────────────────────────────────
    # Handler: new lead arrives
    # ─────────────────────────────────────────────────────────────

    async def _handle_lead_inbound(self, payload: dict[str, Any]) -> None:
        try:
            event = LeadInboundEvent.model_validate(payload)
        except ValidationError as exc:
            log.warning("invalid_lead_inbound", error=str(exc))
            return

        log.info("lead_received", kama_net_id=event.kama_net_id, customer=event.customer_name)

        # Idempotency: skip if we already have a quote for this inquiry
        existing = await get_quote_by_anfrage(self._pool, event.kama_net_id)
        if existing:
            log.info("quote_already_exists", kama_net_id=event.kama_net_id)
            return

        # Step 1 — Qualify
        qualified, reason = qualify(event)
        if not qualified:
            log.info("lead_not_qualified", kama_net_id=event.kama_net_id, reason=reason)
            await kama_net_client.sync_inquiry_status(event.kama_net_id, "qualified", temperature="cold")
            # Emit disqualification so downstream knows
            await self._emit(
                settings.kafka_topic_lead_qualified,
                {
                    "event": "lead.disqualified",
                    "kama_net_id": event.kama_net_id,
                    "reason": reason,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            return

        # Step 2 — Calculate solar offer
        calc = solar_calc(event)
        log.info(
            "solar_calc_done",
            kwp=calc.system_size_kwp,
            yield_kwh=calc.annual_yield_kwh,
            value_chf=calc.quote_value_chf,
        )

        # Step 3 — Build offer document
        markdown = build_offer_markdown(event, calc)
        subject, email_body = build_offer_email(event, calc)
        expires = quote_expires_at()

        # Step 4 — Create quote record
        quote_id = uuid.uuid4()
        sent_at: datetime | None = None
        message_id: str | None = None

        if event.customer_email:
            message_id = send_email(event.customer_email, subject, email_body)
            sent_at = datetime.now(timezone.utc) if message_id else None

        quote_status = "sent" if (message_id or event.customer_email is None) else "draft"

        row = SalesQuoteRow(
            id=quote_id,
            anfrage_kama_net_id=event.kama_net_id,
            customer_name=event.customer_name,
            customer_email=event.customer_email,
            project_type=event.project_type,
            system_size_kwp=calc.system_size_kwp,
            annual_yield_kwh=calc.annual_yield_kwh,
            quote_value_chf=calc.quote_value_chf,
            status=quote_status,
            sent_at=sent_at,
            expires_at=expires,
            body_markdown=markdown,
            email_message_id=message_id,
        )
        await insert_quote(self._pool, row)

        # Step 5 — Schedule follow-ups (only if sent)
        if quote_status == "sent" and event.customer_email:
            await self._schedule_followups(quote_id, event.kama_net_id)

        # Step 6 — Update KAMA-net + emit qualified event
        await kama_net_client.sync_inquiry_status(event.kama_net_id, "quoted", temperature="warm")

        await self._emit(
            settings.kafka_topic_lead_qualified,
            {
                "event": "lead.qualified",
                "kama_net_id": event.kama_net_id,
                "quote_id": str(quote_id),
                "customer_name": event.customer_name,
                "project_type": event.project_type,
                "system_size_kwp": calc.system_size_kwp,
                "quote_value_chf": calc.quote_value_chf,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        if quote_status == "sent":
            await self._emit(
                settings.kafka_topic_offer_sent,
                {
                    "event": "sales.offer_sent",
                    "quote_id": str(quote_id),
                    "kama_net_id": event.kama_net_id,
                    "customer_name": event.customer_name,
                    "customer_email": event.customer_email,
                    "project_type": event.project_type,
                    "system_size_kwp": calc.system_size_kwp,
                    "quote_value_chf": calc.quote_value_chf,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

        log.info(
            "lead_processed",
            kama_net_id=event.kama_net_id,
            quote_id=str(quote_id),
            status=quote_status,
        )

    # ─────────────────────────────────────────────────────────────
    # Handler: incoming reply — detect acceptance/rejection
    # ─────────────────────────────────────────────────────────────

    async def _handle_reply(self, payload: dict[str, Any]) -> None:
        try:
            event = CommReplyReceivedEvent.model_validate(payload)
        except ValidationError as exc:
            log.warning("invalid_comm_reply", error=str(exc))
            return

        if not event.in_reply_to:
            return  # Not a reply to our email

        # Find the quote that owns this email thread
        quote = await get_quote_by_email_message_id(self._pool, event.in_reply_to)
        if not quote:
            log.debug("no_quote_for_reply", in_reply_to=event.in_reply_to)
            return

        if quote["status"] not in ("sent",):
            log.debug("reply_for_non_sent_quote", status=quote["status"])
            return

        body_lower = event.body.lower()
        accepted = any(
            kw in body_lower
            for kw in ("ja", "einverstanden", "bestätige", "auftrag", "zusage", "annehmen", "yes", "accept")
        )
        rejected = any(
            kw in body_lower
            for kw in ("nein", "kein interesse", "ablehnen", "absage", "no thanks", "nicht interessiert")
        )

        now = datetime.now(timezone.utc)
        quote_id = str(quote["id"])

        if accepted:
            log.info("offer_accepted", quote_id=quote_id, customer=quote["customer_name"])
            await update_quote_status(self._pool, quote_id, "accepted", accepted_at=now)
            await cancel_followups_for_quote(self._pool, quote_id)
            await kama_net_client.sync_inquiry_status(
                quote["anfrage_kama_net_id"], "won", temperature="hot"
            )
            await self._convert_to_order(quote)

        elif rejected:
            log.info("offer_rejected", quote_id=quote_id, customer=quote["customer_name"])
            await update_quote_status(self._pool, quote_id, "rejected", rejected_at=now)
            await cancel_followups_for_quote(self._pool, quote_id)
            await kama_net_client.sync_inquiry_status(
                quote["anfrage_kama_net_id"], "lost", temperature="cold"
            )
        else:
            log.info("reply_inconclusive", quote_id=quote_id)

    # ─────────────────────────────────────────────────────────────
    # Convert accepted quote → confirmed order
    # ─────────────────────────────────────────────────────────────

    async def _convert_to_order(self, quote: asyncpg.Record) -> None:
        auftrag_id = await kama_net_client.create_order_in_kama_net(
            anfrage_kama_net_id=quote["anfrage_kama_net_id"],
            customer_name=quote["customer_name"],
            project_type=quote["project_type"],
            system_size_kwp=quote["system_size_kwp"],
            contract_value_chf=quote["quote_value_chf"],
        )

        if not auftrag_id:
            # Generate a local ID if KAMA-net is unavailable
            auftrag_id = f"LOCAL-{uuid.uuid4().hex[:8].upper()}"

        event = OrderConfirmedEvent(
            auftrag_id=auftrag_id,
            anfrage_kama_net_id=quote["anfrage_kama_net_id"],
            customer_name=quote["customer_name"],
            customer_email=quote["customer_email"],
            project_type=quote["project_type"],
            system_size_kwp=quote["system_size_kwp"],
            contract_value_chf=quote["quote_value_chf"],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        await self._emit(settings.kafka_topic_orders_confirmed, event.model_dump())

        # Notify team via communication agent
        notif = CommSendRequest(
            channel="telegram",
            recipient="team",  # communication-agent resolves team chat
            body=(
                f"✅ *Neuer Auftrag bestätigt!*\n"
                f"Kunde: {quote['customer_name']}\n"
                f"Typ: {quote['project_type'].upper()}\n"
                f"Grösse: {quote['system_size_kwp'] or '?'} kWp\n"
                f"Wert: CHF {quote['quote_value_chf']:,.0f}.–\n"
                f"Auftrag-ID: `{auftrag_id}`"
            ),
            context={"auftrag_id": auftrag_id, "quote_id": str(quote["id"])},
        )
        await self._emit(settings.kafka_topic_comm_send, notif.model_dump())

        log.info(
            "order_created",
            auftrag_id=auftrag_id,
            customer=quote["customer_name"],
            value_chf=quote["quote_value_chf"],
        )

    # ─────────────────────────────────────────────────────────────
    # Follow-up scheduling helpers
    # ─────────────────────────────────────────────────────────────

    async def _schedule_followups(
        self, quote_id: uuid.UUID, anfrage_kama_net_id: str
    ) -> None:
        now = datetime.now(timezone.utc)
        followups = [
            SalesFollowupRow(
                id=uuid.uuid4(),
                quote_id=quote_id,
                anfrage_kama_net_id=anfrage_kama_net_id,
                scheduled_at=now + timedelta(days=settings.followup_days_1),
                attempt_number=1,
            ),
            SalesFollowupRow(
                id=uuid.uuid4(),
                quote_id=quote_id,
                anfrage_kama_net_id=anfrage_kama_net_id,
                scheduled_at=now + timedelta(days=settings.followup_days_2),
                attempt_number=2,
            ),
        ]
        for f in followups:
            await insert_followup(self._pool, f)
        log.info(
            "followups_scheduled",
            quote_id=str(quote_id),
            count=len(followups),
            days=[settings.followup_days_1, settings.followup_days_2],
        )

    # ─────────────────────────────────────────────────────────────
    # Periodic follow-up loop (runs in background task)
    # ─────────────────────────────────────────────────────────────

    async def _followup_loop(self) -> None:
        while self._running:
            try:
                await expire_overdue_quotes(self._pool)
                due = await get_due_followups(self._pool)
                for row in due:
                    await self._send_followup(row)
            except Exception as exc:
                log.error("followup_loop_error", error=str(exc), exc_info=True)

            await asyncio.sleep(settings.followup_poll_interval_sec)

    async def _send_followup(self, row: asyncpg.Record) -> None:
        customer_email = row["customer_email"]
        if not customer_email:
            await mark_followup_sent(self._pool, str(row["id"]))
            return

        subject, body = build_followup_email(
            customer_name=row["customer_name"],
            project_type=row["project_type"],
            system_size_kwp=row["system_size_kwp"],
            quote_value_chf=row["quote_value_chf"],
            attempt=row["attempt_number"],
        )

        message_id = send_email(customer_email, subject, body)
        await mark_followup_sent(self._pool, str(row["id"]), message_id)

        log.info(
            "followup_sent",
            followup_id=str(row["id"]),
            customer=row["customer_name"],
            attempt=row["attempt_number"],
        )

        # Emit offer_sent again so dashboards can track follow-up touch
        await self._emit(
            settings.kafka_topic_offer_sent,
            {
                "event": "sales.followup_sent",
                "followup_id": str(row["id"]),
                "quote_id": str(row["quote_id"]),
                "customer_name": row["customer_name"],
                "attempt_number": row["attempt_number"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    # ─────────────────────────────────────────────────────────────
    # Kafka emit helper
    # ─────────────────────────────────────────────────────────────

    async def _emit(self, topic: str, payload: dict[str, Any]) -> None:
        assert self._producer is not None
        await self._producer.send_and_wait(topic, payload)
        log.debug("kafka_emitted", topic=topic, event=payload.get("event"))
