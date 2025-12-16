from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.models.consumption_record import ConsumptionRecord
from app.db.models.print_job import PrintJob
from app.db.models.spool import Spool
from app.schemas.job import JobConsumptionOut, JobOut, ManualConsumptionCreate
from app.services.spool_service import recalc_spool_remaining


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
            select(ConsumptionRecord, Spool)
            .join(Spool, Spool.id == ConsumptionRecord.spool_id)
            .where(ConsumptionRecord.job_id == job_id)
            .order_by(ConsumptionRecord.created_at.asc())
        )
    ).all()

    out: list[JobConsumptionOut] = []
    for c, s in rows:
        out.append(
            JobConsumptionOut(
                id=c.id,
                job_id=c.job_id,
                spool_id=c.spool_id,
                spool_name=s.name,
                spool_material=s.material,
                spool_color=s.color,
                grams=int(c.grams),
                source=c.source,
                confidence=c.confidence,
                created_at=c.created_at,
            )
        )
    return out


@router.post("/{job_id}/consumptions")
async def add_manual_consumption(job_id: UUID, body: ManualConsumptionCreate, db: AsyncSession = Depends(get_db)) -> dict:
    j = await db.get(PrintJob, job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job not found")
    if not await db.get(Spool, body.spool_id):
        raise HTTPException(status_code=404, detail="spool not found")

    c = ConsumptionRecord(
        job_id=job_id,
        spool_id=body.spool_id,
        grams=body.grams,
        source="manual",
        confidence="high",
        created_at=datetime.now(timezone.utc),
    )
    db.add(c)
    await db.flush()
    await recalc_spool_remaining(db, body.spool_id)
    await db.commit()
    return {"ok": True, "consumption_id": str(c.id), "note": body.note}


