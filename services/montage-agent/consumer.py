"""Montage Agent — Kafka consumer + assembly workflow orchestrator."""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import asyncpg
import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.errors import KafkaError
from pydantic import ValidationError

from checklist import build_positions, fetch_material_checklist
from config import settings
from db import (
    complete_positions,
    get_montage_by_auftrag,
    get_montage_by_id,
    get_positions,
    insert_montage_auftrag,
    insert_positions,
    insert_protokoll,
    mark_materials_ready,
    update_montage_status,
)
from models import (
    CommSendRequest,
    MontageAuftragRow,
    MontageProtokollRow,
    MontageProgressEvent,
    OrderConfirmedEvent,
    ProcurementDeliveredEvent,
)
from protocol import (
    build_meldewesen_trigger_payload,
    build_protokoll_body,
    save_protokoll_to_kama_net,
)
from scheduler import assign_technician, fetch_technicians

log = structlog.get_logger()


class MontageAgent:
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
            settings.kafka_topic_orders_confirmed,
            settings.kafka_topic_procurement_delivered,
            settings.kafka_topic_montage_progress,
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
        log.info("montage_agent_started", topics=topics, group=settings.kafka_group_id)

    async def stop(self) -> None:
        self._running = False
        if self._consumer:
            await self._consumer.stop()
        if self._producer:
            await self._producer.stop()
        log.info(
            "montage_agent_stopped",
            received=self.total_received,
            processed=self.total_processed,
            errors=self.total_errors,
        )

    async def run(self) -> None:
        assert self._consumer is not None
        try:
            async for msg in self._consumer:
                await self._handle(msg)
                await self._consumer.commit()
        except asyncio.CancelledError:
            pass
        except KafkaError as exc:
            log.error("kafka_error", exc=str(exc))
            raise

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
            if msg.topic == settings.kafka_topic_orders_confirmed:
                await self._handle_order_confirmed(payload)
            elif msg.topic == settings.kafka_topic_procurement_delivered:
                await self._handle_delivery(payload)
            elif msg.topic == settings.kafka_topic_montage_progress:
                await self._handle_progress(payload)
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
    # Handler: order confirmed → create montage order
    # ─────────────────────────────────────────────────────────────

    async def _handle_order_confirmed(self, payload: dict[str, Any]) -> None:
        try:
            event = OrderConfirmedEvent.model_validate(payload)
        except ValidationError as exc:
            log.warning("invalid_order_confirmed", error=str(exc))
            return

        log.info("order_confirmed_received", auftrag_id=event.auftrag_id)

        # Idempotency: skip if already exists
        existing = await get_montage_by_auftrag(self._pool, event.auftrag_id)
        if existing:
            log.info("montage_already_exists", auftrag_id=event.auftrag_id)
            return

        montage_id = uuid.uuid4()

        # Step 1 — Create montage order in 'planned' state
        row = MontageAuftragRow(
            id=montage_id,
            auftrag_id=event.auftrag_id,
            customer_name=event.customer_name,
            project_type=event.project_type,
            system_size_kwp=event.system_size_kwp,
            status="planned",
        )
        await insert_montage_auftrag(self._pool, row)

        # Step 2 — Load BOM and build position checklist
        materials = await fetch_material_checklist(self._pool, event.auftrag_id)
        positions = build_positions(montage_id, event.project_type, materials)
        await insert_positions(self._pool, positions)

        log.info(
            "montage_order_created",
            auftrag_id=event.auftrag_id,
            montage_id=str(montage_id),
            positions=len(positions),
        )

        # Step 3 — Try to assign technician immediately (if planning horizon allows)
        await self._try_assign(montage_id, event.auftrag_id, event.project_type, event.customer_name)

    # ─────────────────────────────────────────────────────────────
    # Handler: procurement delivered → mark materials ready
    # ─────────────────────────────────────────────────────────────

    async def _handle_delivery(self, payload: dict[str, Any]) -> None:
        try:
            event = ProcurementDeliveredEvent.model_validate(payload)
        except ValidationError as exc:
            log.warning("invalid_procurement_delivered", error=str(exc))
            return

        log.info("delivery_received", auftrag_id=event.auftrag_id)
        record = await mark_materials_ready(self._pool, event.auftrag_id)
        if not record:
            log.warning("montage_not_found_for_delivery", auftrag_id=event.auftrag_id)
            return

        montage_id = uuid.UUID(record["id"])

        # If not yet assigned, try now that materials are ready
        if record["status"] == "planned" and not record["assigned_technician_id"]:
            montage = await get_montage_by_id(self._pool, str(montage_id))
            if montage:
                await self._try_assign(
                    montage_id,
                    event.auftrag_id,
                    montage["project_type"],
                    montage["customer_name"],
                )

    # ─────────────────────────────────────────────────────────────
    # Handler: field progress update
    # ─────────────────────────────────────────────────────────────

    async def _handle_progress(self, payload: dict[str, Any]) -> None:
        try:
            event = MontageProgressEvent.model_validate(payload)
        except ValidationError as exc:
            log.warning("invalid_montage_progress", error=str(exc))
            return

        log.info(
            "progress_update",
            montage_id=event.montage_id,
            completed=len(event.completed_position_ids),
        )

        if event.completed_position_ids:
            await complete_positions(self._pool, event.completed_position_ids)

        # Check if all positions are done → finalize
        positions = await get_positions(self._pool, event.montage_id)
        total = len(positions)
        done = sum(1 for p in positions if p["status"] == "done")

        if total > 0 and done == total:
            await self._finalize_montage(event.montage_id, event.auftrag_id, positions)

    # ─────────────────────────────────────────────────────────────
    # Assignment helper
    # ─────────────────────────────────────────────────────────────

    async def _try_assign(
        self,
        montage_id: uuid.UUID,
        auftrag_id: str,
        project_type: str,
        customer_name: str,
    ) -> None:
        technicians = await fetch_technicians()
        tech, planned_date = assign_technician(
            technicians,
            project_type,
            horizon_days=settings.planning_horizon_days,
            strategy=settings.assignment_strategy,
        )
        if not tech:
            log.warning("no_technician_assigned", auftrag_id=auftrag_id)
            return

        await update_montage_status(
            self._pool,
            str(montage_id),
            "assigned",
            assigned_technician_id=tech.id,
            planned_start_date=planned_date,
        )

        # Notify technician via Telegram (through Communication Agent)
        if tech.telegram_chat_id:
            date_str = planned_date.strftime("%d.%m.%Y") if planned_date else "TBD"
            notif = CommSendRequest(
                channel="telegram",
                recipient=tech.telegram_chat_id,
                body=(
                    f"🔧 *Neuer Montageauftrag*\n"
                    f"Auftrag: `{auftrag_id}`\n"
                    f"Kunde: {customer_name}\n"
                    f"Geplanter Start: {date_str}\n"
                    f"Typ: {project_type.upper()}\n\n"
                    f"Bitte im KAMA-net bestätigen."
                ),
                context={"auftrag_id": auftrag_id, "montage_id": str(montage_id)},
            )
            await self._emit(settings.kafka_topic_comm_send, notif.model_dump())

        # Emit montage.assigned event for downstream (Meldewesen, Lager)
        await self._emit(
            settings.kafka_topic_montage_assigned,
            {
                "event": "montage.assigned",
                "montage_id": str(montage_id),
                "auftrag_id": auftrag_id,
                "technician_id": tech.id,
                "technician_name": tech.name,
                "planned_start_date": planned_date.isoformat() if planned_date else None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        log.info(
            "montage_assigned",
            auftrag_id=auftrag_id,
            technician=tech.name,
            date=planned_date,
        )

    # ─────────────────────────────────────────────────────────────
    # Finalization: all positions done → generate Abnahmeprotokoll
    # ─────────────────────────────────────────────────────────────

    async def _finalize_montage(
        self,
        montage_id: str,
        auftrag_id: str,
        positions: list[asyncpg.Record],
    ) -> None:
        now = datetime.now(timezone.utc)
        montage = await get_montage_by_id(self._pool, montage_id)
        if not montage:
            return

        customer_name = montage["customer_name"]
        tech_id = montage["assigned_technician_id"]

        # Resolve technician name
        tech_name: str | None = None
        if tech_id:
            technicians = await fetch_technicians()
            tech_map = {t.id: t.name for t in technicians}
            tech_name = tech_map.get(tech_id)

        # Generate protocol document
        body = build_protokoll_body(
            auftrag_id=auftrag_id,
            customer_name=customer_name,
            technician_name=tech_name,
            positions=positions,
            completed_at=now,
        )

        prot_id = uuid.uuid4()
        prot_row = MontageProtokollRow(
            id=prot_id,
            montage_id=uuid.UUID(montage_id),
            auftrag_id=auftrag_id,
            customer_name=customer_name,
            technician_id=tech_id,
            technician_name=tech_name,
            completed_positions=len(positions),
            total_positions=len(positions),
            body_markdown=body,
            handed_over_at=now,
        )

        # Persist protocol to DB
        await insert_protokoll(self._pool, prot_row)

        # Try to save to KAMA-net as well
        kama_net_id = await save_protokoll_to_kama_net(prot_row)
        log.info("protokoll_created", id=str(prot_id), kama_net_id=kama_net_id)

        # Mark montage as done
        await update_montage_status(self._pool, montage_id, "done")

        # Notify Meldewesen via Communication Agent
        meldewesen_payload = build_meldewesen_trigger_payload(
            montage_id=montage_id,
            auftrag_id=auftrag_id,
            customer_name=customer_name,
            technician_name=tech_name,
            protokoll_id=str(prot_id),
            completed_at=now,
        )
        await self._emit(settings.kafka_topic_comm_send, meldewesen_payload)

        # Emit montage.completed for all downstream consumers
        await self._emit(
            settings.kafka_topic_montage_completed,
            {
                "event": "montage.completed",
                "montage_id": montage_id,
                "auftrag_id": auftrag_id,
                "customer_name": customer_name,
                "technician_id": tech_id,
                "protokoll_id": str(prot_id),
                "completed_at": now.isoformat(),
            },
        )

        log.info("montage_completed", auftrag_id=auftrag_id, montage_id=montage_id)

    # ─────────────────────────────────────────────────────────────
    # Kafka emit helper
    # ─────────────────────────────────────────────────────────────

    async def _emit(self, topic: str, payload: dict[str, Any]) -> None:
        assert self._producer is not None
        await self._producer.send_and_wait(topic, payload)
        log.debug("kafka_emitted", topic=topic, event=payload.get("event"))
