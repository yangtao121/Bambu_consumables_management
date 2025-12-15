from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.consumption_record import ConsumptionRecord
from app.db.models.normalized_event import NormalizedEvent
from app.db.models.print_job import PrintJob
from app.db.models.tray_mapping import TrayMapping
from app.services.spool_service import recalc_spool_remaining


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _make_job_key(printer_id: uuid.UUID, ev: NormalizedEvent) -> str:
    data = ev.data_json or {}
    gcode_start_time = data.get("gcode_start_time")
    gcode_file = data.get("gcode_file") or ""
    if isinstance(gcode_start_time, (int, float)) and gcode_start_time > 0:
        return f"{printer_id}:{int(gcode_start_time)}:{gcode_file}"
    # 兜底：用 occurred_at（秒级） + 文件名
    return f"{printer_id}:{int(ev.occurred_at.timestamp())}:{gcode_file}"


def _remain_by_tray(data: dict) -> dict[int, float]:
    trays = data.get("ams_trays")
    out: dict[int, float] = {}
    if not isinstance(trays, list):
        return out
    for t in trays:
        if not isinstance(t, dict):
            continue
        tid = t.get("id")
        remain = t.get("remain")
        if isinstance(tid, int) and isinstance(remain, (int, float)):
            out[tid] = float(remain)
    return out


async def _get_active_tray_to_spool(session: AsyncSession, printer_id: uuid.UUID) -> dict[int, str]:
    rows = (
        await session.execute(
            select(TrayMapping).where(TrayMapping.printer_id == printer_id, TrayMapping.unbound_at.is_(None))
        )
    ).scalars().all()
    return {int(r.tray_id): str(r.spool_id) for r in rows}


async def process_event(session: AsyncSession, ev: NormalizedEvent) -> None:
    printer_id = ev.printer_id
    job_key = _make_job_key(printer_id, ev)

    job = (
        await session.execute(select(PrintJob).where(PrintJob.printer_id == printer_id, PrintJob.job_key == job_key))
    ).scalars().first()

    data = ev.data_json or {}
    tray_now = data.get("tray_now")
    file_name = data.get("gcode_file")

    if job is None:
        # 只有收到开始/进度才创建，结束事件也允许创建以便追溯
        job = PrintJob(
            printer_id=printer_id,
            job_key=job_key,
            file_name=file_name,
            status="unknown",
            started_at=ev.occurred_at,
            ended_at=None,
            spool_binding_snapshot_json={},
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        session.add(job)
        await session.flush()

    # 更新基础字段
    if file_name and not job.file_name:
        job.file_name = file_name

    job.updated_at = _utcnow()

    if ev.type == "PrintStarted":
        job.status = "running"
        job.started_at = job.started_at or ev.occurred_at
        tray_to_spool = await _get_active_tray_to_spool(session, printer_id)
        job.spool_binding_snapshot_json = {
            "tray_to_spool": tray_to_spool,
            "tray_now": tray_now,
            "start_remain_by_tray": _remain_by_tray(data),
        }

    elif ev.type in {"PrintProgress", "StateChanged"}:
        if job.status not in {"ended", "failed"}:
            job.status = "running"

    elif ev.type == "PrintEnded":
        job.status = "ended"
        job.ended_at = ev.occurred_at

    elif ev.type == "PrintFailed":
        job.status = "failed"
        job.ended_at = ev.occurred_at

    # 结算：只在结束/失败时尝试生成扣料记录
    if ev.type in {"PrintEnded", "PrintFailed"}:
        snap = job.spool_binding_snapshot_json or {}
        tray_to_spool = snap.get("tray_to_spool") if isinstance(snap.get("tray_to_spool"), dict) else {}
        start_remain_by_tray = snap.get("start_remain_by_tray") if isinstance(snap.get("start_remain_by_tray"), dict) else {}

        spool_id_str = None
        if isinstance(tray_now, int):
            spool_id_str = tray_to_spool.get(str(tray_now)) or tray_to_spool.get(tray_now)

        if spool_id_str:
            spool_uuid = uuid.UUID(str(spool_id_str))
            # 幂等：同 job + spool 若已有记录则不重复写
            exists = await session.scalar(
                select(ConsumptionRecord.id).where(ConsumptionRecord.job_id == job.id, ConsumptionRecord.spool_id == spool_uuid)
            )
            if not exists:
                end_remain_by_tray = _remain_by_tray(data)
                grams = 0
                source = "unknown"
                confidence = "low"

                # 若 start/end remain 都可用，则做差；单位不确定，因此仍标 medium 且允许纠错
                try:
                    if isinstance(tray_now, int):
                        s_val = start_remain_by_tray.get(str(tray_now)) or start_remain_by_tray.get(tray_now)
                        e_val = end_remain_by_tray.get(tray_now)
                        if isinstance(s_val, (int, float)) and isinstance(e_val, (int, float)) and e_val >= 0 and s_val >= e_val:
                            grams = int(s_val - e_val)
                            source = "ams_remain_delta"
                            confidence = "medium"
                except Exception:
                    pass

                c = ConsumptionRecord(
                    job_id=job.id,
                    spool_id=spool_uuid,
                    grams=grams,
                    source=source,
                    confidence=confidence,
                    created_at=_utcnow(),
                )
                session.add(c)
                await session.flush()
                await recalc_spool_remaining(session, spool_uuid)


class EventProcessor:
    def __init__(self, *, poll_interval_sec: float = 2.0) -> None:
        self.poll_interval_sec = poll_interval_sec
        self._last_id = 0
        self._running = False

    async def run(self, session_factory) -> None:
        self._running = True
        while self._running:
            try:
                async with session_factory() as session:
                    await self._tick(session)
            except Exception:
                # 不中断主进程
                import logging

                logging.getLogger("event_processor").exception("event processor tick failed")
            await asyncio.sleep(self.poll_interval_sec)

    async def _tick(self, session: AsyncSession) -> None:
        rows = (
            await session.execute(
                select(NormalizedEvent).where(NormalizedEvent.id > self._last_id).order_by(NormalizedEvent.id.asc()).limit(500)
            )
        ).scalars().all()
        if not rows:
            return

        for ev in rows:
            await process_event(session, ev)
            self._last_id = max(self._last_id, int(ev.id))
        await session.commit()

    def stop(self) -> None:
        self._running = False


