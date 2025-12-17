from __future__ import annotations

# pyright: reportMissingImports=false

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select

_backend_root = Path(__file__).resolve().parents[1]
_default_pythonpath = "/app" if Path("/app/app").exists() else str(_backend_root)
sys.path.insert(0, os.getenv("PYTHONPATH") or _default_pythonpath)

from app.api.routers.jobs import resolve_job_materials
from app.db.models.consumption_record import ConsumptionRecord
from app.db.models.material_ledger import MaterialLedger
from app.db.models.material_stock import MaterialStock
from app.db.models.normalized_event import NormalizedEvent
from app.db.models.printer import Printer
from app.db.models.print_job import PrintJob
from app.db.session import async_session_factory
from app.schemas.job import JobMaterialResolve, JobMaterialResolveItem
from app.services.event_processor import process_event


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


async def _count_consumptions_for_job(session, job_id: uuid.UUID) -> int:
    return int(
        (await session.scalar(select(func.count()).select_from(ConsumptionRecord).where(ConsumptionRecord.job_id == job_id)))
        or 0
    )


async def _sum_consumed_grams_for_job(session, job_id: uuid.UUID) -> int:
    return int(
        (await session.scalar(select(func.coalesce(func.sum(ConsumptionRecord.grams), 0)).where(ConsumptionRecord.job_id == job_id)))
        or 0
    )


async def _sum_ledger_delta_for_job(session, job_id: uuid.UUID) -> int:
    return int(
        (await session.scalar(select(func.coalesce(func.sum(MaterialLedger.delta_grams), 0)).where(MaterialLedger.job_id == job_id)))
        or 0
    )


async def t1_ams_refresh_no_deduct() -> None:
    async with async_session_factory() as session:
        p = await _create_printer(session, "T1")
        color = f"白色-{uuid.uuid4().hex[:6]}"
        s = await _create_stock(
            session,
            material="PLA",
            color=color,
            brand="拓竹",
            remaining_grams=1500,
            roll_weight_grams=1000,
        )
        base = _utcnow()
        task_id = 11001
        job_key = f"{p.id}:{task_id}"

        ev_start = _event(
            printer_id=p.id,
            typ="PrintStarted",
            occurred_at=base,
            data={
                "task_id": task_id,
                "gcode_file": "t1.gcode",
                "tray_now": 0,
                "gcode_state": "RUNNING",
                "ams_trays": [
                    _tray(tray_id=0, material="PLA", color=color, remain=90, official=True),
                ],
            },
        )
        await _ingest_and_process(session, ev_start)

        for i, r in enumerate([89, 88, 87, 86, 85]):
            ev = _event(
                printer_id=p.id,
                typ="PrintProgress",
                occurred_at=base + timedelta(seconds=5 + i),
                data={
                    "task_id": task_id,
                    "gcode_file": "t1.gcode",
                    "tray_now": 0,
                    "gcode_state": "RUNNING",
                    "ams_trays": [_tray(tray_id=0, material="PLA", color=color, remain=r, official=True)],
                },
            )
            await _ingest_and_process(session, ev)

        j = await _job_by_key(session, printer_id=p.id, job_key=job_key)
        assert await _count_consumptions_for_job(session, j.id) == 0
        await session.refresh(s)
        assert int(s.remaining_grams) == 1500
        await session.commit()


async def t2_duplicate_print_ended_idempotent() -> None:
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
                    "ams_trays": [_tray(tray_id=0, material="PLA", color=color, remain=80, official=True)],
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
                    "ams_trays": [_tray(tray_id=0, material="PLA", color=color, remain=60, official=True)],
                },
            ),
        )

        ev_end = _event(
            printer_id=p.id,
            typ="PrintEnded",
            occurred_at=base + timedelta(seconds=20),
            data={"task_id": task_id, "gcode_file": "t2.gcode", "tray_now": 0, "gcode_state": "FINISH"},
        )
        await _ingest_and_process(session, ev_end)
        j = await _job_by_key(session, printer_id=p.id, job_key=job_key)
        c1 = await _count_consumptions_for_job(session, j.id)
        assert c1 == 1
        await session.refresh(s)
        after1 = int(s.remaining_grams)

        # Duplicate end event (different event_id but same job)
        ev_end2 = _event(
            printer_id=p.id,
            typ="PrintEnded",
            occurred_at=base + timedelta(seconds=21),
            data={"task_id": task_id, "gcode_file": "t2.gcode", "tray_now": 0, "gcode_state": "FINISH"},
        )
        await _ingest_and_process(session, ev_end2)
        c2 = await _count_consumptions_for_job(session, j.id)
        assert c2 == 1
        await session.refresh(s)
        assert int(s.remaining_grams) == after1
        await session.commit()


async def t3_replay_same_events_safe() -> None:
    async with async_session_factory() as session:
        p = await _create_printer(session, "T3")
        color = f"白色-{uuid.uuid4().hex[:6]}"
        s = await _create_stock(session, material="PLA", color=color, brand="拓竹", remaining_grams=2000)
        base = _utcnow()
        task_id = 33003
        job_key = f"{p.id}:{task_id}"

        events = [
            _event(
                printer_id=p.id,
                typ="PrintStarted",
                occurred_at=base,
                data={
                    "task_id": task_id,
                    "gcode_file": "t3.gcode",
                    "tray_now": 0,
                    "gcode_state": "RUNNING",
                    "ams_trays": [_tray(tray_id=0, material="PLA", color=color, remain=80, official=True)],
                },
            ),
            _event(
                printer_id=p.id,
                typ="PrintProgress",
                occurred_at=base + timedelta(seconds=10),
                data={
                    "task_id": task_id,
                    "gcode_file": "t3.gcode",
                    "tray_now": 0,
                    "gcode_state": "RUNNING",
                    "ams_trays": [_tray(tray_id=0, material="PLA", color=color, remain=70, official=True)],
                },
            ),
            _event(
                printer_id=p.id,
                typ="PrintEnded",
                occurred_at=base + timedelta(seconds=20),
                data={"task_id": task_id, "gcode_file": "t3.gcode", "tray_now": 0, "gcode_state": "FINISH"},
            ),
        ]

        for ev in events:
            await _ingest_and_process(session, ev)
        j = await _job_by_key(session, printer_id=p.id, job_key=job_key)
        c1 = await _count_consumptions_for_job(session, j.id)
        await session.refresh(s)
        after1 = int(s.remaining_grams)

        # Replay: run process_event again on same in-memory events
        for ev in events:
            await process_event(session, ev)
        c2 = await _count_consumptions_for_job(session, j.id)
        await session.refresh(s)
        after2 = int(s.remaining_grams)

        assert c1 == 1
        assert c2 == 1
        assert after2 == after1
        await session.commit()


async def t4_switch_tray_multi_color() -> None:
    async with async_session_factory() as session:
        p = await _create_printer(session, "T4")
        tag = uuid.uuid4().hex[:6]
        color0 = f"白色-{tag}"
        color1 = f"黑色-{tag}"
        s0 = await _create_stock(session, material="PLA", color=color0, brand="拓竹", remaining_grams=2000)
        s1 = await _create_stock(session, material="PLA", color=color1, brand="拓竹", remaining_grams=2000)
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
                    "ams_trays": [
                        _tray(tray_id=0, material="PLA", color=color0, remain=90, official=True),
                        _tray(tray_id=1, material="PLA", color=color1, remain=90, official=True),
                    ],
                },
            ),
        )

        # Use tray 0
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
                    "ams_trays": [
                        _tray(tray_id=0, material="PLA", color=color0, remain=80, official=True),
                        _tray(tray_id=1, material="PLA", color=color1, remain=90, official=True),
                    ],
                },
            ),
        )
        # Switch to tray 1
        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="PrintProgress",
                occurred_at=base + timedelta(seconds=20),
                data={
                    "task_id": task_id,
                    "gcode_file": "t4.gcode",
                    "tray_now": 1,
                    "gcode_state": "RUNNING",
                    "ams_trays": [
                        _tray(tray_id=0, material="PLA", color=color0, remain=80, official=True),
                        _tray(tray_id=1, material="PLA", color=color1, remain=70, official=True),
                    ],
                },
            ),
        )

        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="PrintEnded",
                occurred_at=base + timedelta(seconds=30),
                data={"task_id": task_id, "gcode_file": "t4.gcode", "tray_now": 1, "gcode_state": "FINISH"},
            ),
        )

        j = await _job_by_key(session, printer_id=p.id, job_key=job_key)
        rows = (
            await session.execute(select(ConsumptionRecord).where(ConsumptionRecord.job_id == j.id).order_by(ConsumptionRecord.tray_id.asc()))
        ).scalars().all()
        assert len(rows) == 2
        assert {r.tray_id for r in rows} == {0, 1}
        await session.refresh(s0)
        await session.refresh(s1)
        assert int(s0.remaining_grams) < 2000
        assert int(s1.remaining_grams) < 2000
        await session.commit()


async def t5_remain_increase_is_ignored_start_end_only() -> None:
    async with async_session_factory() as session:
        p = await _create_printer(session, "T5")
        color = f"白色-{uuid.uuid4().hex[:6]}"
        s = await _create_stock(session, material="PLA", color=color, brand="拓竹", remaining_grams=5000, roll_weight_grams=1000)
        base = _utcnow()
        task_id = 55005
        job_key = f"{p.id}:{task_id}"

        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="PrintStarted",
                occurred_at=base,
                data={
                    "task_id": task_id,
                    "gcode_file": "t5.gcode",
                    "tray_now": 0,
                    "gcode_state": "RUNNING",
                    "ams_trays": [_tray(tray_id=0, material="PLA", color=color, remain=80, official=True)],
                },
            ),
        )
        # Decrease to 20
        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="PrintProgress",
                occurred_at=base + timedelta(seconds=10),
                data={
                    "task_id": task_id,
                    "gcode_file": "t5.gcode",
                    "tray_now": 0,
                    "gcode_state": "RUNNING",
                    "ams_trays": [_tray(tray_id=0, material="PLA", color=color, remain=20, official=True)],
                },
            ),
        )
        # Spool swap: jump up to 95 (should split)
        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="PrintProgress",
                occurred_at=base + timedelta(seconds=20),
                data={
                    "task_id": task_id,
                    "gcode_file": "t5.gcode",
                    "tray_now": 0,
                    "gcode_state": "RUNNING",
                    "ams_trays": [_tray(tray_id=0, material="PLA", color=color, remain=95, official=True)],
                },
            ),
        )
        # Consume new spool down to 60
        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="PrintProgress",
                occurred_at=base + timedelta(seconds=30),
                data={
                    "task_id": task_id,
                    "gcode_file": "t5.gcode",
                    "tray_now": 0,
                    "gcode_state": "RUNNING",
                    "ams_trays": [_tray(tray_id=0, material="PLA", color=color, remain=60, official=True)],
                },
            ),
        )
        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="PrintEnded",
                occurred_at=base + timedelta(seconds=40),
                data={"task_id": task_id, "gcode_file": "t5.gcode", "tray_now": 0, "gcode_state": "FINISH"},
            ),
        )

        j = await _job_by_key(session, printer_id=p.id, job_key=job_key)
        rows = (await session.execute(select(ConsumptionRecord).where(ConsumptionRecord.job_id == j.id))).scalars().all()
        assert len(rows) == 1
        assert int(rows[0].segment_idx or 0) == 0
        assert int(rows[0].grams) == 200  # only start-end: 80% -> 60% of 1000g
        await session.refresh(s)
        assert int(s.remaining_grams) == 5000 - 200
        await session.commit()


async def t6_pending_resolve_repeat_idempotent() -> None:
    async with async_session_factory() as session:
        p = await _create_printer(session, "T6")
        color = f"红色-{uuid.uuid4().hex[:6]}"
        # Two third-party brands with same material+color => auto-resolve should fail (pending)
        s_a = await _create_stock(session, material="PLA", color=color, brand="BrandA", remaining_grams=2000)
        s_b = await _create_stock(session, material="PLA", color=color, brand="BrandB", remaining_grams=2000)
        s_a_id = s_a.id
        s_b_id = s_b.id
        base = _utcnow()
        task_id = 66006
        job_key = f"{p.id}:{task_id}"

        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="PrintStarted",
                occurred_at=base,
                data={
                    "task_id": task_id,
                    "gcode_file": "t6.gcode",
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
                typ="PrintProgress",
                occurred_at=base + timedelta(seconds=10),
                data={
                    "task_id": task_id,
                    "gcode_file": "t6.gcode",
                    "tray_now": 0,
                    "gcode_state": "RUNNING",
                    "ams_trays": [_tray(tray_id=0, material="PLA", color=color, remain=80, official=False)],
                },
            ),
        )
        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="PrintEnded",
                occurred_at=base + timedelta(seconds=20),
                data={"task_id": task_id, "gcode_file": "t6.gcode", "tray_now": 0, "gcode_state": "FINISH"},
            ),
        )

        j = await _job_by_key(session, printer_id=p.id, job_key=job_key)
        job_id = j.id
        await session.commit()  # commit before resolve

    # Resolve pending twice by calling router directly to validate idempotency without running HTTP server
    async with async_session_factory() as session:
        body = JobMaterialResolve(items=[JobMaterialResolveItem(tray_id=0, stock_id=s_a_id)])
        r1 = await resolve_job_materials(job_id, body, session)
        assert r1.get("ok") is True
        r2 = await resolve_job_materials(job_id, body, session)
        assert r2.get("ok") is True

    async with async_session_factory() as session:
        # Still only one segment consumption
        rows = (
            await session.execute(select(ConsumptionRecord).where(ConsumptionRecord.job_id == job_id).order_by(ConsumptionRecord.created_at.asc()))
        ).scalars().all()
        assert len(rows) == 1
        assert int(rows[0].tray_id or 0) == 0
        assert int(rows[0].segment_idx or 0) == 0
        assert rows[0].stock_id == s_a_id

        sa = await session.get(MaterialStock, s_a_id)
        sb = await session.get(MaterialStock, s_b_id)
        assert sa is not None and sb is not None
        assert int(sa.remaining_grams) == 2000 - int(rows[0].grams)
        assert int(sb.remaining_grams) == 2000
        await session.commit()


async def t8_state_changed_finish_still_settles() -> None:
    """
    Simulate collector restart: FINISH arrives as StateChanged (no PrintEnded).
    Settlement must still happen.
    """
    async with async_session_factory() as session:
        p = await _create_printer(session, "T8")
        color = f"白色-{uuid.uuid4().hex[:6]}"
        s = await _create_stock(session, material="PLA", color=color, brand="拓竹", remaining_grams=2000, roll_weight_grams=1000)
        base = _utcnow()
        task_id = 88008
        job_key = f"{p.id}:{task_id}"

        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="PrintStarted",
                occurred_at=base,
                data={
                    "task_id": task_id,
                    "gcode_file": "t8.gcode",
                    "tray_now": 0,
                    "gcode_state": "RUNNING",
                    "ams_trays": [_tray(tray_id=0, material="PLA", color=color, remain=80, official=True)],
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
                    "gcode_file": "t8.gcode",
                    "tray_now": 0,
                    "gcode_state": "RUNNING",
                    "ams_trays": [_tray(tray_id=0, material="PLA", color=color, remain=70, official=True)],
                },
            ),
        )

        # No PrintEnded; only StateChanged with FINISH and no ams_trays.
        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="StateChanged",
                occurred_at=base + timedelta(seconds=20),
                data={"task_id": task_id, "gcode_file": "t8.gcode", "tray_now": 0, "gcode_state": "FINISH"},
            ),
        )

        j = await _job_by_key(session, printer_id=p.id, job_key=job_key)
        rows = (await session.execute(select(ConsumptionRecord).where(ConsumptionRecord.job_id == j.id))).scalars().all()
        assert len(rows) == 1
        assert int(rows[0].grams) == 100  # 80% -> 70% of 1000g
        await session.refresh(s)
        assert int(s.remaining_grams) == 2000 - 100
        await session.commit()


async def t7_clamp_to_zero_consistent() -> None:
    async with async_session_factory() as session:
        p = await _create_printer(session, "T7")
        color = f"白色-{uuid.uuid4().hex[:6]}"
        s = await _create_stock(session, material="PLA", color=color, brand="拓竹", remaining_grams=50, roll_weight_grams=1000)
        base = _utcnow()
        task_id = 77007
        job_key = f"{p.id}:{task_id}"

        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="PrintStarted",
                occurred_at=base,
                data={
                    "task_id": task_id,
                    "gcode_file": "t7.gcode",
                    "tray_now": 0,
                    "gcode_state": "RUNNING",
                    "ams_trays": [_tray(tray_id=0, material="PLA", color=color, remain=300, official=True)],
                },
            ),
        )
        # Consume 120g (grams unit)
        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="PrintProgress",
                occurred_at=base + timedelta(seconds=10),
                data={
                    "task_id": task_id,
                    "gcode_file": "t7.gcode",
                    "tray_now": 0,
                    "gcode_state": "RUNNING",
                    "ams_trays": [_tray(tray_id=0, material="PLA", color=color, remain=180, official=True)],
                },
            ),
        )
        await _ingest_and_process(
            session,
            _event(
                printer_id=p.id,
                typ="PrintEnded",
                occurred_at=base + timedelta(seconds=20),
                data={"task_id": task_id, "gcode_file": "t7.gcode", "tray_now": 0, "gcode_state": "FINISH"},
            ),
        )

        j = await _job_by_key(session, printer_id=p.id, job_key=job_key)
        rows = (await session.execute(select(ConsumptionRecord).where(ConsumptionRecord.job_id == j.id))).scalars().all()
        assert len(rows) == 1
        c = rows[0]
        assert int(c.grams_requested or 0) >= 120
        assert int(c.grams_effective or 0) == 50
        assert int(c.grams) == 50

        await session.refresh(s)
        assert int(s.remaining_grams) == 0

        led_sum = await _sum_ledger_delta_for_job(session, j.id)
        assert led_sum == -50
        await session.commit()


async def main() -> None:
    tests = [
        ("T1 refresh no deduct", t1_ams_refresh_no_deduct),
        ("T2 duplicate ended idempotent", t2_duplicate_print_ended_idempotent),
        ("T3 replay safe", t3_replay_same_events_safe),
        ("T4 switch tray", t4_switch_tray_multi_color),
        ("T5 remain increase ignored (start-end only)", t5_remain_increase_is_ignored_start_end_only),
        ("T6 pending resolve repeat", t6_pending_resolve_repeat_idempotent),
        ("T7 clamp to zero", t7_clamp_to_zero_consistent),
        ("T8 StateChanged FINISH still settles", t8_state_changed_finish_still_settles),
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


if __name__ == "__main__":
    asyncio.run(main())
