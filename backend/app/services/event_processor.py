from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.consumption_record import ConsumptionRecord
from app.db.models.ams_color_mapping import AmsColorMapping
from app.db.models.material_stock import MaterialStock
from app.db.models.normalized_event import NormalizedEvent
from app.db.models.print_job import PrintJob
from app.services.stock_service import apply_stock_delta


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_tray_now(v: object) -> int | None:
    """
    Payload tray_now is sometimes a numeric string; 255 usually means "no active tray".
    """
    n: int | None = None
    if isinstance(v, int):
        n = v
    elif isinstance(v, str):
        s = v.strip()
        if s.isdigit():
            try:
                n = int(s)
            except Exception:
                n = None
    if n == 255:
        return None
    return n


def _make_job_key(printer_id: uuid.UUID, ev: NormalizedEvent) -> str:
    data = ev.data_json or {}
    task_id = data.get("task_id") or data.get("subtask_id")
    if isinstance(task_id, (int, float)) and task_id:
        return f"{printer_id}:{int(task_id)}"
    if isinstance(task_id, str) and task_id.strip():
        return f"{printer_id}:{task_id.strip()}"
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


_OFFICIAL_BRAND = "拓竹"


def _normalize_color_to_hex_or_name(v: object) -> tuple[str | None, str | None]:
    """
    Normalize AMS tray color:
    - If v is 6/8-hex like 'FFFFFF'/'FFFFFFFF' (optionally with '#'), return (color_hex='#RRGGBB', color_name=None)
    - Otherwise treat it as a human color name string and return (None, color_name)
    """
    if not isinstance(v, str):
        return (None, None)
    s = v.strip()
    if not s:
        return (None, None)
    hx = s[1:].strip() if s.startswith("#") else s
    hx_u = hx.upper()
    is_hex = all(c in "0123456789ABCDEF" for c in hx_u)
    if is_hex and len(hx_u) == 8:
        return (f"#{hx_u[-6:]}", None)
    if is_hex and len(hx_u) == 6:
        return (f"#{hx_u}", None)
    return (None, s)


def _is_official_tray(t: dict) -> bool:
    """
    Heuristic: Official/Bambu filament trays often carry RFID identifiers.
    If we see any of these fields, treat as official.
    """
    tag_uid = t.get("tag_uid")
    tray_uuid = t.get("tray_uuid")
    tray_id_name = t.get("tray_id_name")
    if isinstance(tag_uid, (int, float)) and tag_uid > 0:
        return True
    if isinstance(tag_uid, str) and tag_uid.strip() and tag_uid.strip() not in {"0", "00000000"}:
        return True
    if isinstance(tray_uuid, str) and tray_uuid.strip():
        return True
    if isinstance(tray_id_name, str) and tray_id_name.strip():
        # Some firmwares put RFID/name here; treat non-empty as a hint.
        return True
    return False


def _tray_meta_by_tray(data: dict) -> dict[int, dict]:
    trays = data.get("ams_trays")
    out: dict[int, dict] = {}
    if not isinstance(trays, list):
        return out

    for t in trays:
        if not isinstance(t, dict):
            continue
        tid = t.get("id")
        if not isinstance(tid, int):
            continue
        material = t.get("type")
        color_hex, color_name = _normalize_color_to_hex_or_name(t.get("color"))
        meta = {
            "material": material if isinstance(material, str) else None,
            # Stock matching key: mapped color name (e.g. '白色'). Might be None when unmapped.
            "color": color_name,
            # Raw/normalized AMS hex color (e.g. '#FFFFFF') if available
            "color_hex": color_hex,
            "is_official": _is_official_tray(t),
            "tag_uid": t.get("tag_uid"),
            "tray_uuid": t.get("tray_uuid"),
            "tray_id_name": t.get("tray_id_name"),
        }
        out[int(tid)] = meta
    return out


async def _hydrate_tray_color_names(session: AsyncSession, tm: dict) -> dict:
    """
    Fill meta['color'] from persisted mapping by meta['color_hex'] when possible.
    Returns a shallow-copied dict to avoid mutating JSONB snapshots in-place.
    """
    out: dict = {}
    for k, v in (tm or {}).items():
        if not isinstance(v, dict):
            out[k] = v
            continue
        meta = dict(v)
        if not meta.get("color") and isinstance(meta.get("color_hex"), str) and meta["color_hex"].startswith("#"):
            name = await session.scalar(
                select(AmsColorMapping.color_name).where(AmsColorMapping.color_hex == meta["color_hex"]).limit(1)
            )
            if isinstance(name, str) and name.strip():
                meta["color"] = name.strip()
        out[k] = meta
    return out


async def _resolve_stock_id(session: AsyncSession, *, material: str | None, color: str | None, is_official: bool) -> uuid.UUID | None:
    if not material or not color:
        return None
    if is_official:
        rows = (
            await session.execute(
                select(MaterialStock).where(
                    MaterialStock.material == material, MaterialStock.color == color, MaterialStock.brand == _OFFICIAL_BRAND
                )
            )
        ).scalars().all()
        if len(rows) == 1:
            return rows[0].id
        return None
    # third-party: brand unknown; only auto-resolve when unique under same material+color
    rows = (
        await session.execute(
            select(MaterialStock).where(
                MaterialStock.material == material, MaterialStock.color == color, MaterialStock.brand != _OFFICIAL_BRAND
            )
        )
    ).scalars().all()
    if len(rows) == 1:
        return rows[0].id
    return None


def _normalize_remain_value(v: object) -> tuple[str, float] | None:
    """
    Normalize AMS tray remain to a comparable unit.

    Heuristic:
    - v in [0, 1]   -> percent fraction, convert to 0~100
    - v in (1, 100] -> percent 0~100
    - v > 100       -> treat as grams-like absolute unit
    """
    if not isinstance(v, (int, float)):
        return None
    fv = float(v)
    if fv < 0:
        return None
    if fv <= 1.0:
        return ("pct", fv * 100.0)
    if fv <= 100.0:
        return ("pct", fv)
    return ("grams", fv)


async def process_event(session: AsyncSession, ev: NormalizedEvent) -> None:
    printer_id = ev.printer_id
    job_key = _make_job_key(printer_id, ev)

    job = (
        await session.execute(select(PrintJob).where(PrintJob.printer_id == printer_id, PrintJob.job_key == job_key))
    ).scalars().first()

    data = ev.data_json or {}
    tray_now = _normalize_tray_now(data.get("tray_now"))
    file_name = data.get("gcode_file")
    gcode_state = data.get("gcode_state")

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
        tray_meta_by_tray = await _hydrate_tray_color_names(session, _tray_meta_by_tray(data))
        tray_to_stock: dict[str, str] = {}
        pending_trays: list[int] = []
        for tray_id, meta in tray_meta_by_tray.items():
            # 空槽/未知槽：不参与归因与 pending（避免把 AMS 空位当成“待归因”）
            if not meta.get("material") or (not meta.get("color") and not meta.get("color_hex")):
                continue
            sid = None
            if meta.get("color"):
                sid = await _resolve_stock_id(
                    session,
                    material=meta.get("material"),
                    color=meta.get("color"),
                    is_official=bool(meta.get("is_official")),
                )
            if sid:
                tray_to_stock[str(tray_id)] = str(sid)
            else:
                pending_trays.append(int(tray_id))
        trays_seen: list[int] = [int(tray_now)] if isinstance(tray_now, int) else []
        job.spool_binding_snapshot_json = {
            "mode": "stock",
            "tray_to_stock": tray_to_stock,
            "tray_now": tray_now,
            "start_remain_by_tray": _remain_by_tray(data),
            "trays_seen": trays_seen,
            "tray_meta_by_tray": tray_meta_by_tray,
            "pending_trays": sorted(set(pending_trays)),
            "pending_consumptions": [],
        }

    elif ev.type in {"PrintProgress", "StateChanged"}:
        # Use gcode_state as source-of-truth to avoid "FINISH but running" on cold start.
        if isinstance(gcode_state, str):
            if gcode_state in {"FINISH", "IDLE"}:
                job.status = "ended"
                job.ended_at = job.ended_at or ev.occurred_at
            elif gcode_state in {"FAILED", "STOPPED", "CANCELED"}:
                job.status = "failed"
                job.ended_at = job.ended_at or ev.occurred_at
            else:
                if job.status not in {"ended", "failed"}:
                    job.status = "running"
        else:
            if job.status not in {"ended", "failed"}:
                job.status = "running"

        # Cold-start / mid-print takeover: if snapshot missing, initialize from current progress event.
        # This enables "正在打印"的情况下也能在结束时结算扣料（精度受接管时点影响，但比完全不结算更好）。
        snap = job.spool_binding_snapshot_json or {}
        if (
            job.status == "running"
            and (not isinstance(snap, dict) or snap.get("mode") != "stock" or "start_remain_by_tray" not in snap)
        ):
            tray_meta_by_tray = await _hydrate_tray_color_names(session, _tray_meta_by_tray(data))
            tray_to_stock: dict[str, str] = {}
            pending_trays: list[int] = []
            for tray_id, meta in tray_meta_by_tray.items():
                if not meta.get("material") or (not meta.get("color") and not meta.get("color_hex")):
                    continue
                sid = None
                if meta.get("color"):
                    sid = await _resolve_stock_id(
                        session,
                        material=meta.get("material"),
                        color=meta.get("color"),
                        is_official=bool(meta.get("is_official")),
                    )
                if sid:
                    tray_to_stock[str(tray_id)] = str(sid)
                else:
                    pending_trays.append(int(tray_id))
            trays_seen: list[int] = [int(tray_now)] if isinstance(tray_now, int) else []
            job.spool_binding_snapshot_json = {
                "mode": "stock",
                "tray_to_stock": tray_to_stock,
                "tray_now": tray_now,
                "start_remain_by_tray": _remain_by_tray(data),
                "trays_seen": trays_seen,
                "tray_meta_by_tray": tray_meta_by_tray,
                "pending_trays": sorted(set(pending_trays)),
                "pending_consumptions": [],
            }

        # Track trays seen during the print (multi-color / tray switch)
        if job.status == "running" and isinstance(tray_now, int):
            snap = job.spool_binding_snapshot_json or {}
            seen = snap.get("trays_seen")
            seen_set: set[int] = set()
            if isinstance(seen, list):
                for x in seen:
                    try:
                        seen_set.add(int(x))
                    except Exception:
                        pass
            seen_set.add(int(tray_now))
            snap2 = dict(snap)
            snap2["trays_seen"] = sorted(seen_set)

            # Refresh tray meta (color/material can appear later), and try to auto-resolve new trays.
            tm = await _hydrate_tray_color_names(session, _tray_meta_by_tray(data))
            old_tm = snap2.get("tray_meta_by_tray") if isinstance(snap2.get("tray_meta_by_tray"), dict) else {}
            merged_tm = dict(old_tm)
            for k, v in tm.items():
                merged_tm[str(int(k))] = v
            merged_tm = await _hydrate_tray_color_names(session, merged_tm)
            snap2["tray_meta_by_tray"] = merged_tm

            # IMPORTANT: copy nested dict/list to avoid in-place mutations on JSONB snapshot
            tray_to_stock = (
                dict(snap2.get("tray_to_stock")) if isinstance(snap2.get("tray_to_stock"), dict) else {}
            )
            pending = snap2.get("pending_trays") if isinstance(snap2.get("pending_trays"), list) else []
            pending_set: set[int] = set()
            for p in pending:
                try:
                    pending_set.add(int(p))
                except Exception:
                    pass

            # Attempt resolving for trays we have meta for but not yet mapped.
            for tray_id in seen_set:
                if str(tray_id) in tray_to_stock:
                    continue
                meta = merged_tm.get(str(tray_id))
                if isinstance(meta, dict):
                    if not meta.get("material") or (not meta.get("color") and not meta.get("color_hex")):
                        # 空槽/未知槽不参与 pending
                        continue
                    sid = None
                    if meta.get("color"):
                        sid = await _resolve_stock_id(
                            session,
                            material=meta.get("material"),
                            color=meta.get("color"),
                            is_official=bool(meta.get("is_official")),
                        )
                    if sid:
                        tray_to_stock[str(tray_id)] = str(sid)
                        if tray_id in pending_set:
                            pending_set.remove(tray_id)
                    else:
                        pending_set.add(int(tray_id))
            snap2["tray_to_stock"] = tray_to_stock
            snap2["pending_trays"] = sorted(pending_set)
            job.spool_binding_snapshot_json = snap2

    elif ev.type == "PrintEnded":
        job.status = "ended"
        job.ended_at = ev.occurred_at

    elif ev.type == "PrintFailed":
        job.status = "failed"
        job.ended_at = ev.occurred_at

    # 结算：只在结束/失败时尝试生成扣料记录
    if ev.type in {"PrintEnded", "PrintFailed"}:
        snap = job.spool_binding_snapshot_json or {}
        # IMPORTANT: copy nested dict/list to avoid in-place mutations on JSONB snapshot
        tray_to_stock = dict(snap.get("tray_to_stock")) if isinstance(snap.get("tray_to_stock"), dict) else {}
        start_remain_by_tray = (
            dict(snap.get("start_remain_by_tray")) if isinstance(snap.get("start_remain_by_tray"), dict) else {}
        )
        trays_seen = list(snap.get("trays_seen")) if isinstance(snap.get("trays_seen"), list) else []
        tray_meta_by_tray = dict(snap.get("tray_meta_by_tray")) if isinstance(snap.get("tray_meta_by_tray"), dict) else {}
        pending_consumptions = list(snap.get("pending_consumptions")) if isinstance(snap.get("pending_consumptions"), list) else []
        tray_meta_by_tray = await _hydrate_tray_color_names(session, tray_meta_by_tray)

        snap_tray_now = _normalize_tray_now(snap.get("tray_now"))
        effective_tray_now = tray_now if tray_now is not None else snap_tray_now

        trays_set: set[int] = set()
        for t in trays_seen:
            try:
                trays_set.add(int(t))
            except Exception:
                pass
        # Always include the last-known tray as a fallback.
        if isinstance(effective_tray_now, int):
            trays_set.add(int(effective_tray_now))
        trays_to_settle = sorted(trays_set)

        end_remain_by_tray = _remain_by_tray(data)
        # 结束事件可能不包含 AMS 托盘细节：回溯最近事件找一条有 remain 的
        if not end_remain_by_tray:
            recent = (
                await session.execute(
                    select(NormalizedEvent)
                    .where(NormalizedEvent.printer_id == printer_id)
                    .order_by(NormalizedEvent.occurred_at.desc(), NormalizedEvent.id.desc())
                    .limit(20)
                )
            ).scalars().all()
            for rev in recent:
                rb = _remain_by_tray(rev.data_json or {})
                if rb:
                    end_remain_by_tray = rb
                    break

        for tray_id in trays_to_settle:
            s_raw = start_remain_by_tray.get(str(tray_id)) or start_remain_by_tray.get(tray_id)
            e_raw = end_remain_by_tray.get(tray_id)

            grams = 0
            pct_delta: float | None = None
            source = "unknown"
            confidence = "low"

            s_nv = _normalize_remain_value(s_raw)
            e_nv = _normalize_remain_value(e_raw)
            if s_nv and e_nv and s_nv[0] == e_nv[0]:
                unit = s_nv[0]
                s_val = float(s_nv[1])
                e_val = float(e_nv[1])
                if s_val >= e_val:
                    if unit == "pct":
                        pct_delta = s_val - e_val
                        source = "ams_remain_delta_pct"
                        confidence = "medium"
                    elif unit == "grams":
                        delta = int(round(s_val - e_val))
                        if delta >= 0:
                            grams = delta
                            source = "ams_remain_delta_grams"
                            confidence = "medium"

            # No effective consumption detected
            if source == "ams_remain_delta_pct":
                if pct_delta is None or pct_delta <= 0:
                    continue
            else:
                if grams <= 0:
                    continue

            # Try to determine stock_id for this tray
            stock_id_str = tray_to_stock.get(str(tray_id)) or tray_to_stock.get(tray_id)
            stock_uuid: uuid.UUID | None = None
            if stock_id_str:
                try:
                    stock_uuid = uuid.UUID(str(stock_id_str))
                except Exception:
                    stock_uuid = None

            # If not mapped yet, attempt resolve using tray meta.
            if stock_uuid is None:
                meta = tray_meta_by_tray.get(str(tray_id)) or tray_meta_by_tray.get(tray_id)
                if isinstance(meta, dict):
                    sid = None
                    if meta.get("color"):
                        sid = await _resolve_stock_id(
                            session,
                            material=meta.get("material"),
                            color=meta.get("color"),
                            is_official=bool(meta.get("is_official")),
                        )
                    if sid:
                        stock_uuid = sid
                        tray_to_stock[str(tray_id)] = str(sid)

            if stock_uuid is None:
                # Pending attribution: record pct delta or grams delta for later settlement
                meta = tray_meta_by_tray.get(str(tray_id)) or tray_meta_by_tray.get(tray_id) or {}
                if not (
                    isinstance(meta, dict)
                    and meta.get("material")
                    and (meta.get("color") or meta.get("color_hex"))
                ):
                    continue
                eff_conf = "low" if (not meta.get("color") and meta.get("color_hex")) else confidence
                pending_consumptions.append(
                    {
                        "tray_id": int(tray_id),
                        "unit": s_nv[0] if s_nv else None,
                        "start": s_nv[1] if s_nv else None,
                        "end": e_nv[1] if e_nv else None,
                        "grams": int(grams) if source == "ams_remain_delta_grams" else None,
                        "pct_delta": float(pct_delta) if source == "ams_remain_delta_pct" and pct_delta is not None else None,
                        "source": source,
                        "confidence": eff_conf,
                        "material": meta.get("material"),
                        "color": meta.get("color"),
                        "color_hex": meta.get("color_hex"),
                        "is_official": bool(meta.get("is_official")),
                    }
                )
                continue

            # Idempotent: same job + tray + stock
            exists = await session.scalar(
                select(ConsumptionRecord.id).where(
                    ConsumptionRecord.job_id == job.id,
                    ConsumptionRecord.stock_id == stock_uuid,
                    ConsumptionRecord.tray_id == int(tray_id),
                )
            )
            if exists:
                continue

            # For pct unit, convert using stock.roll_weight_grams
            if source == "ams_remain_delta_pct":
                stock = await session.get(MaterialStock, stock_uuid)
                if not stock:
                    continue
                grams = int(round((float(pct_delta or 0.0) / 100.0) * float(stock.roll_weight_grams)))
                if grams <= 0:
                    continue

            await apply_stock_delta(
                session,
                stock_uuid,
                -int(grams),
                reason=f"consumption job={job.id} tray={int(tray_id)} source={source}",
                job_id=job.id,
            )

            c = ConsumptionRecord(
                job_id=job.id,
                spool_id=None,
                stock_id=stock_uuid,
                tray_id=int(tray_id),
                grams=int(grams),
                source=source,
                confidence=confidence,
                created_at=_utcnow(),
            )
            session.add(c)
            await session.flush()

        # Persist any snapshot updates (tray_to_stock/pending_consumptions)
        snap2 = dict(snap)
        snap2["tray_to_stock"] = tray_to_stock
        snap2["pending_consumptions"] = pending_consumptions
        # recompute pending_trays for UI
        pending_set: set[int] = set()
        for pc in pending_consumptions:
            if isinstance(pc, dict) and "tray_id" in pc:
                try:
                    pending_set.add(int(pc["tray_id"]))
                except Exception:
                    pass
        snap2["pending_trays"] = sorted(pending_set)
        job.spool_binding_snapshot_json = snap2


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


