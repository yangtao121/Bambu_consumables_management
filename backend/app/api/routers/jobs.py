from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.models.consumption_record import ConsumptionRecord
from app.db.models.material_stock import MaterialStock
from app.db.models.print_job import PrintJob
from app.db.models.spool import Spool
from app.schemas.job import JobConsumptionOut, JobMaterialResolve, JobOut, ManualConsumptionCreate, ManualConsumptionVoid
from app.services.stock_service import apply_stock_delta


router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobOut])
async def list_jobs(
    printer_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[PrintJob]:
    stmt = select(PrintJob)
    if printer_id is not None:
        stmt = stmt.where(PrintJob.printer_id == printer_id)
    if status is not None:
        stmt = stmt.where(PrintJob.status == status)
    stmt = stmt.order_by(PrintJob.started_at.desc())
    return (await db.execute(stmt)).scalars().all()


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: UUID, db: AsyncSession = Depends(get_db)) -> PrintJob:
    j = await db.get(PrintJob, job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job not found")
    return j


@router.get("/{job_id}/consumptions", response_model=list[JobConsumptionOut])
async def list_job_consumptions(job_id: UUID, db: AsyncSession = Depends(get_db)) -> list[JobConsumptionOut]:
    if not await db.get(PrintJob, job_id):
        raise HTTPException(status_code=404, detail="job not found")

    rows = (
        await db.execute(
            select(ConsumptionRecord, Spool, MaterialStock)
            .outerjoin(Spool, Spool.id == ConsumptionRecord.spool_id)
            .outerjoin(MaterialStock, MaterialStock.id == ConsumptionRecord.stock_id)
            .where(ConsumptionRecord.job_id == job_id)
            .order_by(ConsumptionRecord.created_at.asc())
        )
    ).all()

    out: list[JobConsumptionOut] = []
    for c, s, st in rows:
        out.append(
            JobConsumptionOut(
                id=c.id,
                job_id=c.job_id,
                tray_id=getattr(c, "tray_id", None),
                stock_id=getattr(c, "stock_id", None),
                material=(st.material if st else (s.material if s else None)),
                color=(st.color if st else (s.color if s else None)),
                brand=(st.brand if st else (s.brand if s else None)),
                spool_id=(c.spool_id if getattr(c, "spool_id", None) else None),
                spool_name=(s.name if s else None),
                spool_material=(s.material if s else None),
                spool_color=(s.color if s else None),
                grams=int(c.grams),
                source=c.source,
                confidence=c.confidence,
                created_at=c.created_at,
                voided_at=getattr(c, "voided_at", None),
                void_reason=getattr(c, "void_reason", None),
            )
        )
    return out


@router.post("/{job_id}/consumptions")
async def add_manual_consumption(job_id: UUID, body: ManualConsumptionCreate, db: AsyncSession = Depends(get_db)) -> dict:
    j = await db.get(PrintJob, job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job not found")
    st = await db.get(MaterialStock, body.stock_id)
    if not st:
        raise HTTPException(status_code=404, detail="stock not found")

    grams_requested = int(body.grams)
    grams_effective = min(int(grams_requested), int(st.remaining_grams))
    if grams_effective <= 0:
        raise HTTPException(status_code=409, detail="stock has no remaining grams")

    c = ConsumptionRecord(
        job_id=job_id,
        spool_id=None,
        stock_id=body.stock_id,
        tray_id=None,
        segment_idx=None,
        grams=int(grams_effective),
        grams_requested=int(grams_requested),
        grams_effective=int(grams_effective),
        source="manual",
        confidence="high",
        created_at=datetime.now(timezone.utc),
    )
    db.add(c)
    await db.flush()
    await apply_stock_delta(
        db,
        body.stock_id,
        -int(grams_effective),
        reason=f"manual consumption={c.id} job={job_id} note={body.note or ''}",
        job_id=job_id,
        kind="consumption",
    )
    await db.commit()
    return {"ok": True, "consumption_id": str(c.id), "note": body.note}


@router.post("/{job_id}/consumptions/{consumption_id}/void")
async def void_manual_job_consumption(
    job_id: UUID,
    consumption_id: UUID,
    body: ManualConsumptionVoid,
    db: AsyncSession = Depends(get_db),
) -> dict:
    j = await db.get(PrintJob, job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job not found")

    c = await db.get(ConsumptionRecord, consumption_id)
    if not c or c.job_id != job_id:
        raise HTTPException(status_code=404, detail="consumption not found")
    if getattr(c, "voided_at", None) is not None:
        raise HTTPException(status_code=409, detail="consumption already voided")
    if str(c.source or "") != "manual":
        raise HTTPException(status_code=409, detail="only manual consumptions can be voided")
    if c.stock_id is None:
        raise HTTPException(status_code=409, detail="manual consumption missing stock_id")

    grams = int(getattr(c, "grams_effective", None) or getattr(c, "grams") or 0)
    if grams <= 0:
        raise HTTPException(status_code=409, detail="invalid consumption grams")

    now = datetime.now(timezone.utc)
    c.voided_at = now
    c.void_reason = body.reason

    await apply_stock_delta(
        db,
        c.stock_id,
        +int(grams),
        reason=f"void manual job={job_id} consumption={consumption_id} note={body.reason or ''}",
        job_id=job_id,
        kind="reversal",
    )
    await db.commit()
    return {"ok": True}


@router.post("/{job_id}/materials/resolve")
async def resolve_job_materials(job_id: UUID, body: JobMaterialResolve, db: AsyncSession = Depends(get_db)) -> dict:
    j = await db.get(PrintJob, job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job not found")

    snap = j.spool_binding_snapshot_json or {}
    pending = snap.get("pending_consumptions") if isinstance(snap.get("pending_consumptions"), list) else []
    if not pending:
        return {"ok": True, "resolved": 0, "note": "no pending consumptions"}

    tray_to_stock = snap.get("tray_to_stock") if isinstance(snap.get("tray_to_stock"), dict) else {}

    resolved_count = 0
    remaining_pending: list[dict] = []

    # Build quick lookup mapping tray -> stock_id (from request)
    req_map: dict[int, UUID] = {}
    for it in body.items or []:
        req_map[int(it.tray_id)] = it.stock_id

    for entry in pending:
        if not isinstance(entry, dict):
            continue
        tray_id = entry.get("tray_id")
        try:
            tray_id_int = int(tray_id)
        except Exception:
            remaining_pending.append(entry)
            continue
        try:
            segment_idx = int(entry.get("segment_idx") or 0)
        except Exception:
            segment_idx = 0

        stock_id = req_map.get(tray_id_int)
        if not stock_id:
            remaining_pending.append(entry)
            continue

        st = await db.get(MaterialStock, stock_id)
        if not st:
            remaining_pending.append(entry)
            continue

        unit = entry.get("unit")
        grams_requested = 0
        if unit == "grams":
            try:
                grams_requested = int(entry.get("grams_requested") or entry.get("grams") or 0)
            except Exception:
                grams_requested = 0
        elif unit == "pct":
            try:
                pct_delta = float(entry.get("pct_delta") or 0.0)
            except Exception:
                pct_delta = 0.0
            grams_requested = int(round((pct_delta / 100.0) * float(st.roll_weight_grams)))

        if grams_requested <= 0:
            # nothing to settle; drop it
            resolved_count += 1
            continue

        # Segment-idempotent: same job+tray+segment only once (prevents double deduction when mapping changes)
        exists = await db.scalar(
            select(ConsumptionRecord.id).where(
                ConsumptionRecord.job_id == job_id,
                ConsumptionRecord.tray_id == tray_id_int,
                ConsumptionRecord.segment_idx == segment_idx,
            )
        )
        if exists:
            resolved_count += 1
            continue

        grams_effective = min(int(grams_requested), int(st.remaining_grams))
        if grams_effective <= 0:
            resolved_count += 1
            continue

        await apply_stock_delta(
            db,
            stock_id,
            -int(grams_effective),
            reason=f"resolve job={job_id} tray={tray_id_int} source={entry.get('source')}",
            job_id=job_id,
            kind="consumption",
        )

        c = ConsumptionRecord(
            job_id=job_id,
            spool_id=None,
            stock_id=stock_id,
            tray_id=tray_id_int,
            segment_idx=int(segment_idx),
            grams=int(grams_effective),
            grams_requested=int(grams_requested),
            grams_effective=int(grams_effective),
            source=str(entry.get("source") or "resolved_pending"),
            confidence=str(entry.get("confidence") or "low"),
            created_at=datetime.now(timezone.utc),
        )
        db.add(c)
        await db.flush()

        tray_to_stock[str(tray_id_int)] = str(stock_id)
        resolved_count += 1

    # Update snapshot
    snap2 = dict(snap)
    snap2["pending_consumptions"] = remaining_pending
    pending_set: set[int] = set()
    for e in remaining_pending:
        if isinstance(e, dict) and "tray_id" in e:
            try:
                pending_set.add(int(e["tray_id"]))
            except Exception:
                pass
    snap2["pending_trays"] = sorted(pending_set)
    snap2["tray_to_stock"] = tray_to_stock
    j.spool_binding_snapshot_json = snap2
    j.updated_at = datetime.now(timezone.utc)

    await db.commit()
    return {"ok": True, "resolved": resolved_count, "remaining_pending": len(remaining_pending)}


