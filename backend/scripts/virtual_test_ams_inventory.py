from __future__ import annotations

# pyright: reportMissingImports=false

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import func, select

_backend_root = Path(__file__).resolve().parents[1]
_default_pythonpath = "/app" if Path("/app/app").exists() else str(_backend_root)
sys.path.insert(0, os.getenv("PYTHONPATH") or _default_pythonpath)

from app.api.routers.jobs import add_manual_consumption, resolve_job_materials, void_manual_job_consumption
from app.api.routers.material_ledger import reverse_ledger_row
from app.api.routers.stocks import add_manual_stock_consumption, update_stock, void_manual_stock_consumption
from app.db.models.consumption_record import ConsumptionRecord
from app.db.models.material_ledger import MaterialLedger
from app.db.models.material_stock import MaterialStock
from app.db.models.normalized_event import NormalizedEvent
from app.db.models.printer import Printer
from app.db.models.print_job import PrintJob
from app.db.session import async_session_factory
from app.schemas.job import JobMaterialResolve, JobMaterialResolveItem, ManualConsumptionCreate, ManualConsumptionVoid
from app.schemas.stock import StockManualConsumptionCreate, StockUpdate, VoidRequest
from app.services.event_processor import process_event
from app.services.stock_service import apply_stock_delta


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _eid(prefix: str) -> str:
    return f"{prefix}:{uuid.uuid4()}"


def _event(
    *,
    printer_id: uuid.UUID,
    typ: str,
    occurred_at: datetime,
    data: dict,
    event_id: str | None = None,
) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=event_id or _eid(typ),
        printer_id=printer_id,
        type=typ,
        occurred_at=occurred_at,
        data_json=data,
        raw_event_id=None,
        created_at=_utcnow(),
    )


def _tray(
    *,
    tray_id: int,
    material: str,
    color: str,
    remain: float,
    official: bool = True,
) -> dict:
    t = {
        "id": int(tray_id),
        "type": material,
        "color": color,
        "remain": remain,
    }
    if official:
        t["tray_uuid"] = f"test-{tray_id}-{uuid.uuid4()}"
    return t


def _filament_item(*, tray_id: int | None, typ: str, color_hex: str | None, total_g: float) -> dict:
    # Normalized filament estimate item (collector injects something compatible with this shape)
    it: dict = {
        "tray_id": tray_id,
        "type": typ,
        "total_g": float(total_g),
    }
    if color_hex is not None:
        it["color_hex"] = color_hex
    return it


async def _create_printer(session, alias: str) -> Printer:
    now = _utcnow()
    p = Printer(
        ip="0.0.0.0",
        serial=f"VTEST-{uuid.uuid4().hex[:12]}",
        alias=alias,
        model="virtual",
        lan_access_code_enc="",  # not used in this test
        status="unknown",
        last_seen=None,
        created_at=now,
        updated_at=now,
    )
    session.add(p)
    await session.flush()
    return p


async def _create_job(session, *, printer_id: uuid.UUID, job_key: str = "manual-job", file_name: str = "manual.gcode") -> PrintJob:
    now = _utcnow()
    j = PrintJob(
        printer_id=printer_id,
        job_key=job_key,
        file_name=file_name,
        status="manual",
        started_at=now,
        ended_at=None,
        spool_binding_snapshot_json={},
        created_at=now,
        updated_at=now,
    )
    session.add(j)
    await session.flush()
    return j


async def _create_stock(
    session,
    *,
    material: str,
    color: str,
    brand: str,
    remaining_grams: int,
    roll_weight_grams: int = 1000,
) -> MaterialStock:
    now = _utcnow()
    s = MaterialStock(
        material=material,
        color=color,
        brand=brand,
        roll_weight_grams=int(roll_weight_grams),
        remaining_grams=int(remaining_grams),
        is_archived=False,
        archived_at=None,
        created_at=now,
        updated_at=now,
    )
    session.add(s)
    await session.flush()
    return s


async def _ingest_and_process(session, ev: NormalizedEvent) -> None:
    session.add(ev)
    await session.flush()
    await process_event(session, ev)


async def _job_by_key(session, *, printer_id: uuid.UUID, job_key: str) -> PrintJob:
    j = (
        (await session.execute(select(PrintJob).where(PrintJob.printer_id == printer_id, PrintJob.job_key == job_key)))
    ).scalars().first()
    assert j is not None
    return j


async def _ledger_rows_for_job(session, job_id: uuid.UUID) -> list[MaterialLedger]:
    return (
        (
            await session.execute(
                select(MaterialLedger)
                .where(MaterialLedger.job_id == job_id)
                .order_by(MaterialLedger.created_at.asc(), MaterialLedger.id.asc())
            )
        )
        .scalars()
        .all()
    )


async def _consumption_rows_for_job(session, job_id: uuid.UUID) -> list[ConsumptionRecord]:
    return (
        (
            await session.execute(
                select(ConsumptionRecord)
                .where(ConsumptionRecord.job_id == job_id)
                .order_by(ConsumptionRecord.tray_id.asc(), ConsumptionRecord.segment_idx.asc())
            )
        )
        .scalars()
        .all()
    )


async def _sum_ledger_delta_for_job(session, job_id: uuid.UUID) -> int:
    return int(
        (await session.scalar(select(func.coalesce(func.sum(MaterialLedger.delta_grams), 0)).where(MaterialLedger.job_id == job_id)))
        or 0
    )


async def _sum_consumed_grams_for_job(session, job_id: uuid.UUID) -> int:
    return int(
        (
            await session.scalar(
                select(func.coalesce(func.sum(ConsumptionRecord.grams), 0)).where(ConsumptionRecord.job_id == job_id)
            )
        )
        or 0
    )


async def _assert_pre_deduct_settlement(
    session,
    *,
    job: PrintJob,
    expected_reserved_by_tray: dict[int, int],
    expected_used_by_tray: dict[int, int],
    expect_cancelled: bool,
) -> None:
    # snapshot settled marker
    snap = job.spool_binding_snapshot_json or {}
    assert isinstance(snap, dict)
    assert snap.get("settled_at") is not None
    assert snap.get("settle_error") is None

    # consumption records
    cons = await _consumption_rows_for_job(session, job.id)
    actual_trays = {int(c.tray_id) if c.tray_id is not None else -1 for c in cons}
    expected_trays = set(expected_used_by_tray.keys())
    if actual_trays != expected_trays:
        led = await _ledger_rows_for_job(session, job.id)
        raise AssertionError(
            {
                "message": "consumption tray set mismatch",
                "expected_trays": sorted(expected_trays),
                "actual_trays": sorted(actual_trays),
                "consumption_rows": [
                    {
                        "id": str(c.id),
                        "tray_id": c.tray_id,
                        "segment_idx": c.segment_idx,
                        "grams": int(c.grams or 0),
                        "grams_requested": int(c.grams_requested or 0),
                        "source": c.source,
                    }
                    for c in cons
                ],
                "ledger_rows": [
                    {"id": str(r.id), "kind": r.kind, "delta_grams": int(r.delta_grams or 0), "reason": r.reason}
                    for r in led
                ],
                "job_status": job.status,
                "job_snapshot": job.spool_binding_snapshot_json,
            }
        )
    for c in cons:
        if c.tray_id is None:
            led = await _ledger_rows_for_job(session, job.id)
            raise AssertionError(
                {
                    "message": "consumption row has null tray_id",
                    "consumption_rows": [
                        {
                            "id": str(x.id),
                            "tray_id": x.tray_id,
                            "segment_idx": x.segment_idx,
                            "grams": int(x.grams or 0),
                            "grams_requested": int(x.grams_requested or 0),
                            "source": x.source,
                        }
                        for x in cons
                    ],
                    "ledger_rows": [
                        {"id": str(r.id), "kind": r.kind, "delta_grams": int(r.delta_grams or 0), "reason": r.reason}
                        for r in led
                    ],
                    "job_status": job.status,
                    "job_snapshot": job.spool_binding_snapshot_json,
                }
            )
        tid = int(c.tray_id)
        assert int(c.segment_idx or 0) == 0
        assert int(c.grams) == int(expected_used_by_tray[tid])
        assert int(c.grams_effective or c.grams) == int(expected_used_by_tray[tid])
        assert int(c.grams_requested or 0) == int(expected_reserved_by_tray[tid])
        assert (c.source or "").startswith("mqtt_filament_total_g") or (c.source or "").startswith(
            "reservation_estimate"
        )

    # ledger rows
    led = await _ledger_rows_for_job(session, job.id)
    cons_led = [r for r in led if (r.kind or "") == "consumption"]
    rev_led = [r for r in led if (r.kind or "") == "reversal"]
    assert len(cons_led) == len(expected_reserved_by_tray)

    # each tray must have one consumption ledger row with delta=-reserved
    for tid, grams_reserved in expected_reserved_by_tray.items():
        matched = [
            r
            for r in cons_led
            if (r.reason or "").find(f"tray={int(tid)}") >= 0 and int(r.delta_grams) == -int(grams_reserved)
        ]
        assert len(matched) == 1

    if expect_cancelled:
        # reversal delta == refunded grams
        for tid, grams_reserved in expected_reserved_by_tray.items():
            used = int(expected_used_by_tray.get(int(tid), 0))
            refund = int(grams_reserved - used)
            if refund <= 0:
                continue
            matched = [
                r
                for r in rev_led
                if (r.reason or "").find(f"cancel_refund") >= 0
                and (r.reason or "").find(f"tray={int(tid)}") >= 0
                and int(r.delta_grams) == int(refund)
            ]
            assert len(matched) == 1
    else:
        assert len(rev_led) == 0

    # net ledger delta should equal -sum(used)
    assert int(await _sum_ledger_delta_for_job(session, job.id)) == -int(sum(expected_used_by_tray.values()))
    assert int(await _sum_consumed_grams_for_job(session, job.id)) == int(sum(expected_used_by_tray.values()))


async def t1_pre_deduct_reserve_then_end_converts() -> None:
    async with async_session_factory() as session:
        p = await _create_printer(session, "T1")
        color = f"白色-{uuid.uuid4().hex[:6]}"
        s = await _create_stock(session, material="PLA", color=color, brand="拓竹", remaining_grams=2000)
        base = _utcnow()
        task_id = 11001
        job_key = f"{p.id}:{task_id}"

        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="PrintStarted",
                occurred_at=base,
                data={
                    "task_id": task_id,
                    "gcode_file": "t1.gcode",
                    "tray_now": 0,
                    "gcode_state": "RUNNING",
                    "ams_trays": [_tray(tray_id=0, material="PLA", color=color, remain=90, official=True)],
                },
            ),
        )

        # First progress brings filament estimate => reserve 120g
        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="PrintProgress",
                occurred_at=base + timedelta(seconds=10),
                data={
                    "task_id": task_id,
                    "gcode_file": "t1.gcode",
                    "tray_now": 0,
                    "gcode_state": "RUNNING",
                    "percent": 5,
                    "ams_trays": [_tray(tray_id=0, material="PLA", color=color, remain=90, official=True)],
                    "filament": [_filament_item(tray_id=0, typ="PLA", color_hex=None, total_g=120.0)],
                },
            ),
        )
        await session.refresh(s)
        assert int(s.remaining_grams) == 2000 - 120

        # End converts reservation->consumption and creates consumption_record (no extra stock delta)
        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="PrintEnded",
                occurred_at=base + timedelta(seconds=20),
                data={"task_id": task_id, "gcode_file": "t1.gcode", "tray_now": 0, "gcode_state": "FINISH"},
            ),
        )

        j = await _job_by_key(session, printer_id=p.id, job_key=job_key)
        await _assert_pre_deduct_settlement(
            session,
            job=j,
            expected_reserved_by_tray={0: 120},
            expected_used_by_tray={0: 120},
            expect_cancelled=False,
        )
        await session.refresh(s)
        assert int(s.remaining_grams) == 2000 - 120
        await session.commit()


async def t2_duplicate_end_idempotent() -> None:
    async with async_session_factory() as session:
        p = await _create_printer(session, "T2")
        color = f"白色-{uuid.uuid4().hex[:6]}"
        s = await _create_stock(session, material="PLA", color=color, brand="拓竹", remaining_grams=2000)
        base = _utcnow()
        task_id = 22002
        job_key = f"{p.id}:{task_id}"

        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="PrintStarted",
                occurred_at=base,
                data={
                    "task_id": task_id,
                    "gcode_file": "t2.gcode",
                    "tray_now": 0,
                    "gcode_state": "RUNNING",
                    "ams_trays": [_tray(tray_id=0, material="PLA", color=color, remain=90, official=True)],
                },
            ),
        )
        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="PrintProgress",
                occurred_at=base + timedelta(seconds=10),
                data={
                    "task_id": task_id,
                    "gcode_file": "t2.gcode",
                    "tray_now": 0,
                    "gcode_state": "RUNNING",
                    "percent": 10,
                    "ams_trays": [_tray(tray_id=0, material="PLA", color=color, remain=90, official=True)],
                    "filament": [_filament_item(tray_id=0, typ="PLA", color_hex=None, total_g=80.0)],
                },
            ),
        )
        await session.refresh(s)
        assert int(s.remaining_grams) == 2000 - 80

        ev_end = _event(
            printer_id=p.id,
            typ="PrintEnded",
            occurred_at=base + timedelta(seconds=20),
            data={"task_id": task_id, "gcode_file": "t2.gcode", "tray_now": 0, "gcode_state": "FINISH"},
        )
        await _ingest_and_process(session, ev_end)
        j = await _job_by_key(session, printer_id=p.id, job_key=job_key)
        await _assert_pre_deduct_settlement(
            session,
            job=j,
            expected_reserved_by_tray={0: 80},
            expected_used_by_tray={0: 80},
            expect_cancelled=False,
        )
        await session.refresh(s)
        after1 = int(s.remaining_grams)

        # Duplicate end event (different event_id)
        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="PrintEnded",
                occurred_at=base + timedelta(seconds=21),
                data={"task_id": task_id, "gcode_file": "t2.gcode", "tray_now": 0, "gcode_state": "FINISH"},
            ),
        )
        j2 = await _job_by_key(session, printer_id=p.id, job_key=job_key)
        await _assert_pre_deduct_settlement(
            session,
            job=j2,
            expected_reserved_by_tray={0: 80},
            expected_used_by_tray={0: 80},
            expect_cancelled=False,
        )
        await session.refresh(s)
        assert int(s.remaining_grams) == after1
        await session.commit()


async def t3_cancel_partial_refund_by_progress() -> None:
    async with async_session_factory() as session:
        p = await _create_printer(session, "T3")
        color = f"白色-{uuid.uuid4().hex[:6]}"
        s = await _create_stock(session, material="PLA", color=color, brand="拓竹", remaining_grams=2000)
        base = _utcnow()
        task_id = 33003
        job_key = f"{p.id}:{task_id}"

        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="PrintStarted",
                occurred_at=base,
                data={
                    "task_id": task_id,
                    "gcode_file": "t3.gcode",
                    "tray_now": 0,
                    "gcode_state": "RUNNING",
                    "ams_trays": [_tray(tray_id=0, material="PLA", color=color, remain=90, official=True)],
                },
            ),
        )

        # Reserve 100g
        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="PrintProgress",
                occurred_at=base + timedelta(seconds=10),
                data={
                    "task_id": task_id,
                    "gcode_file": "t3.gcode",
                    "tray_now": 0,
                    "gcode_state": "RUNNING",
                    "mc_percent": 0,
                    "ams_trays": [_tray(tray_id=0, material="PLA", color=color, remain=90, official=True)],
                    "filament": [_filament_item(tray_id=0, typ="PLA", color_hex=None, total_g=100.0)],
                },
            ),
        )
        await session.refresh(s)
        assert int(s.remaining_grams) == 2000 - 100

        # Later progress says 30% then cancelled
        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="PrintProgress",
                occurred_at=base + timedelta(seconds=20),
                data={
                    "task_id": task_id,
                    "gcode_file": "t3.gcode",
                    "tray_now": 0,
                    "gcode_state": "RUNNING",
                    "mc_percent": 30,
                    "ams_trays": [_tray(tray_id=0, material="PLA", color=color, remain=90, official=True)],
                },
            ),
        )
        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="StateChanged",
                occurred_at=base + timedelta(seconds=25),
                data={
                    "task_id": task_id,
                    "gcode_file": "t3.gcode",
                    "tray_now": 0,
                    "gcode_state": "CANCELED",
                    "mc_percent": 30,
                },
            ),
        )

        j = await _job_by_key(session, printer_id=p.id, job_key=job_key)
        assert (j.status or "") == "cancelled"

        # Reserved 100g, used 30g => refund 70g => net -30g
        await _assert_pre_deduct_settlement(
            session,
            job=j,
            expected_reserved_by_tray={0: 100},
            expected_used_by_tray={0: 30},
            expect_cancelled=True,
        )
        await session.refresh(s)
        assert int(s.remaining_grams) == 2000 - 30
        await session.commit()


async def t4_strict_no_fallback_single_filament_still_reserves() -> None:
    async with async_session_factory() as session:
        p = await _create_printer(session, "T4")
        color = f"白色-{uuid.uuid4().hex[:6]}"
        s = await _create_stock(session, material="PLA", color=color, brand="拓竹", remaining_grams=500)
        base = _utcnow()
        task_id = 44004
        job_key = f"{p.id}:{task_id}"

        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="PrintStarted",
                occurred_at=base,
                data={
                    "task_id": task_id,
                    "gcode_file": "t4.gcode",
                    "tray_now": 0,
                    "gcode_state": "RUNNING",
                    "ams_trays": [_tray(tray_id=0, material="PLA", color=color, remain=90, official=True)],
                },
            ),
        )

        # tray_id missing but single filament item + strict_no_fallback=true => should fallback to tray_now
        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="PrintProgress",
                occurred_at=base + timedelta(seconds=10),
                data={
                    "task_id": task_id,
                    "gcode_file": "t4.gcode",
                    "tray_now": 0,
                    "gcode_state": "RUNNING",
                    "filament_strict_no_fallback": True,
                    "ams_trays": [_tray(tray_id=0, material="PLA", color=color, remain=90, official=True)],
                    "filament": [_filament_item(tray_id=None, typ="PLA", color_hex=None, total_g=60.0)],
                },
            ),
        )
        await session.refresh(s)
        assert int(s.remaining_grams) == 500 - 60

        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="PrintEnded",
                occurred_at=base + timedelta(seconds=20),
                data={"task_id": task_id, "gcode_file": "t4.gcode", "tray_now": 0, "gcode_state": "FINISH"},
            ),
        )
        j = await _job_by_key(session, printer_id=p.id, job_key=job_key)
        await _assert_pre_deduct_settlement(
            session,
            job=j,
            expected_reserved_by_tray={0: 60},
            expected_used_by_tray={0: 60},
            expect_cancelled=False,
        )
        await session.commit()


async def t5_reverse_adjustment_endpoint() -> None:
    async with async_session_factory() as session:
        _p = await _create_printer(session, "T5")
        color = f"黑色-{uuid.uuid4().hex[:6]}"
        s = await _create_stock(session, material="PLA", color=color, brand="拓竹", remaining_grams=500)
        await session.commit()

        before = int(s.remaining_grams)
        # Create adjustment +120g
        await apply_stock_delta(session, s.id, +120, reason="t5 adjustment", job_id=None, kind="adjustment")
        await session.commit()
        await session.refresh(s)
        assert int(s.remaining_grams) == before + 120

        adj = (
            (
                await session.execute(
                    select(MaterialLedger)
                    .where(MaterialLedger.stock_id == s.id, MaterialLedger.kind == "adjustment")
                    .order_by(MaterialLedger.created_at.desc())
                )
            )
            .scalars()
            .first()
        )
        assert adj is not None

        res = await reverse_ledger_row(adj.id, VoidRequest(reason="t5 reverse"), db=session)
        assert res.get("ok") is True
        await session.refresh(s)
        assert int(s.remaining_grams) == before

        adj2 = await session.get(MaterialLedger, adj.id)
        assert adj2 is not None and adj2.voided_at is not None
        rev = (
            (
                await session.execute(
                    select(MaterialLedger).where(MaterialLedger.reversal_of_id == adj.id).order_by(MaterialLedger.created_at.desc())
                )
            )
            .scalars()
            .first()
        )
        assert rev is not None
        assert int(rev.delta_grams) == -int(adj.delta_grams)
        assert (rev.kind or "") == "reversal"

        # Unsafe reversal should be blocked if adjustment grams were consumed.
        s2 = await _create_stock(session, material="PLA", color=f"灰-{uuid.uuid4().hex[:6]}", brand="拓竹", remaining_grams=50)
        await apply_stock_delta(session, s2.id, +100, reason="t5 adj2", job_id=None, kind="adjustment")
        await session.commit()
        # Consume most of it (so remaining < 100)
        await add_manual_stock_consumption(s2.id, StockManualConsumptionCreate(grams=120, note="consume"), db=session)
        await session.refresh(s2)
        assert int(s2.remaining_grams) < 100
        adj_bad = (
            (
                await session.execute(
                    select(MaterialLedger)
                    .where(MaterialLedger.stock_id == s2.id, MaterialLedger.kind == "adjustment")
                    .order_by(MaterialLedger.created_at.desc())
                )
            )
            .scalars()
            .first()
        )
        assert adj_bad is not None
        try:
            await reverse_ledger_row(adj_bad.id, VoidRequest(reason="should fail"), db=session)
            raise AssertionError("expected reverse to be blocked")
        except HTTPException as e:
            assert int(e.status_code) == 409


async def t6_stock_rename_merge() -> None:
    async with async_session_factory() as session:
        _p = await _create_printer(session, "T6")
        a = await _create_stock(session, material="PLA", color=f"白-{uuid.uuid4().hex[:6]}", brand="拓竹", remaining_grams=400)
        b = await _create_stock(session, material="PLA", color=f"合并色-{uuid.uuid4().hex[:6]}", brand="拓竹", remaining_grams=100)
        await session.commit()

        res = await update_stock(
            a.id,
            StockUpdate(material=b.material, color=b.color, brand=b.brand, roll_weight_grams=b.roll_weight_grams),
            merge=True,
            db=session,
        )
        assert res is not None
        await session.refresh(b)
        assert int(b.remaining_grams) == 500
        await session.refresh(a)
        assert bool(a.is_archived) is True
        await session.commit()


async def t7_job_manual_consumption_void() -> None:
    async with async_session_factory() as session:
        p = await _create_printer(session, "T7")
        j = await _create_job(session, printer_id=p.id, job_key=f"MANUAL-{uuid.uuid4()}")
        s = await _create_stock(session, material="PLA", color=f"红-{uuid.uuid4().hex[:6]}", brand="拓竹", remaining_grams=300)
        await session.commit()

        before = int(s.remaining_grams)
        res = await add_manual_consumption(j.id, ManualConsumptionCreate(stock_id=s.id, grams=120, note="t7"), db=session)
        cid = uuid.UUID(str(res["consumption_id"]))
        await session.refresh(s)
        assert int(s.remaining_grams) == before - 120

        await void_manual_job_consumption(j.id, cid, ManualConsumptionVoid(reason="t7 void"), db=session)
        await session.refresh(s)
        assert int(s.remaining_grams) == before
        c = await session.get(ConsumptionRecord, cid)
        assert c is not None and c.voided_at is not None
        await session.commit()


async def t8_manual_stock_consumption_void_roundtrip() -> None:
    async with async_session_factory() as session:
        p = await _create_printer(session, "T8")
        _ = p
        s = await _create_stock(session, material="PLA", color=f"白色-{uuid.uuid4().hex[:6]}", brand="拓竹", remaining_grams=1000)
        await session.commit()

        before = int(s.remaining_grams)
        res = await add_manual_stock_consumption(s.id, StockManualConsumptionCreate(grams=200, note="t8"), db=session)
        cid = uuid.UUID(str(res["consumption_id"]))

        await session.refresh(s)
        assert int(s.remaining_grams) == before - 200

        await void_manual_stock_consumption(s.id, cid, VoidRequest(reason="t8 void"), db=session)
        await session.refresh(s)
        assert int(s.remaining_grams) == before

        c = await session.get(ConsumptionRecord, cid)
        assert c is not None
        assert c.voided_at is not None
        await session.commit()


async def t9_pending_resolve_repeat_idempotent() -> None:
    """Pending resolve still works with explicit tray->stock mapping."""
    async with async_session_factory() as session:
        p = await _create_printer(session, "T9")
        color = f"红色-{uuid.uuid4().hex[:6]}"
        # Two third-party brands with same material+color => auto-resolve should fail (pending)
        s_a = await _create_stock(session, material="PLA", color=color, brand="BrandA", remaining_grams=2000)
        s_b = await _create_stock(session, material="PLA", color=color, brand="BrandB", remaining_grams=2000)
        s_a_id = s_a.id
        _ = s_b
        base = _utcnow()
        task_id = 99009
        job_key = f"{p.id}:{task_id}"

        # Start without reservation; end will settle with missing_reservation, but pending resolve should still create ledger+record
        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="PrintStarted",
                occurred_at=base,
                data={
                    "task_id": task_id,
                    "gcode_file": "t9.gcode",
                    "tray_now": 0,
                    "gcode_state": "RUNNING",
                    "ams_trays": [_tray(tray_id=0, material="PLA", color=color, remain=90, official=False)],
                },
            ),
        )
        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="StateChanged",
                occurred_at=base + timedelta(seconds=5),
                data={"task_id": task_id, "gcode_file": "t9.gcode", "tray_now": 0, "gcode_state": "FINISH"},
            ),
        )
        j = await _job_by_key(session, printer_id=p.id, job_key=job_key)
        job_id = j.id
        await session.commit()

    async with async_session_factory() as session:
        body = JobMaterialResolve(items=[JobMaterialResolveItem(tray_id=0, stock_id=s_a_id)])
        r1 = await resolve_job_materials(job_id, body, session)
        assert r1.get("ok") is True
        r2 = await resolve_job_materials(job_id, body, session)
        assert r2.get("ok") is True
        await session.commit()


async def main() -> None:
    tests = [
        ("T1 reserve->end converts", t1_pre_deduct_reserve_then_end_converts),
        ("T2 duplicate end idempotent", t2_duplicate_end_idempotent),
        ("T3 cancel refund by progress", t3_cancel_partial_refund_by_progress),
        ("T4 strict single filament fallback", t4_strict_no_fallback_single_filament_still_reserves),
        ("T5 reverse adjustment endpoint", t5_reverse_adjustment_endpoint),
        ("T6 stock rename merge", t6_stock_rename_merge),
        ("T7 job manual consumption void", t7_job_manual_consumption_void),
        ("T8 manual stock consumption void", t8_manual_stock_consumption_void_roundtrip),
        ("T9 pending resolve repeat", t9_pending_resolve_repeat_idempotent),
    ]

    fails: list[str] = []
    for name, fn in tests:
        try:
            await fn()
            print(f"[OK] {name}")
        except Exception as e:
            fails.append(name)
            import traceback

            print(f"[FAIL] {name}: {e!r}")
            print(traceback.format_exc())

    if fails:
        raise SystemExit(f"failed: {fails}")
    print(f"[SUMMARY] ran {len(tests)} tests")


if __name__ == "__main__":
    asyncio.run(main())
