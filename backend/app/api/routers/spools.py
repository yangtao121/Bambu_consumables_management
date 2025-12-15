from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.models.consumption_record import ConsumptionRecord
from app.db.models.inventory_adjustment import InventoryAdjustment
from app.db.models.spool import Spool
from app.db.models.tray_mapping import TrayMapping
from app.schemas.spool import (
    LedgerRow,
    SpoolAdjustmentCreate,
    SpoolCreate,
    SpoolMarkEmpty,
    SpoolOut,
    SpoolUpdate,
)
from app.services.spool_service import recalc_spool_remaining


router = APIRouter(prefix="/spools", tags=["spools"])


@router.get("", response_model=list[SpoolOut])
async def list_spools(db: AsyncSession = Depends(get_db)) -> list[Spool]:
    return (await db.execute(select(Spool).order_by(Spool.created_at.desc()))).scalars().all()


@router.post("", response_model=SpoolOut)
async def create_spool(body: SpoolCreate, db: AsyncSession = Depends(get_db)) -> Spool:
    now = datetime.now(timezone.utc)
    s = Spool(
        name=body.name,
        material=body.material,
        color=body.color,
        brand=body.brand,
        diameter_mm=body.diameter_mm,
        initial_grams=body.initial_grams,
        tare_grams=body.tare_grams,
        price_total=body.price_total,
        price_per_kg=body.price_per_kg,
        purchase_date=body.purchase_date,
        note=body.note,
        status="active",
        remaining_grams_est=body.initial_grams,
        created_at=now,
        updated_at=now,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


@router.get("/{spool_id}", response_model=SpoolOut)
async def get_spool(spool_id: UUID, db: AsyncSession = Depends(get_db)) -> Spool:
    s = await db.get(Spool, spool_id)
    if not s:
        raise HTTPException(status_code=404, detail="spool not found")
    return s


@router.patch("/{spool_id}", response_model=SpoolOut)
async def update_spool(spool_id: UUID, body: SpoolUpdate, db: AsyncSession = Depends(get_db)) -> Spool:
    s = await db.get(Spool, spool_id)
    if not s:
        raise HTTPException(status_code=404, detail="spool not found")

    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    s.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(s)
    return s


@router.post("/{spool_id}/mark-empty")
async def mark_empty(spool_id: UUID, body: SpoolMarkEmpty, db: AsyncSession = Depends(get_db)) -> dict:
    s = await db.get(Spool, spool_id)
    if not s:
        raise HTTPException(status_code=404, detail="spool not found")
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirm required")

    now = datetime.now(timezone.utc)
    s.status = "empty"
    s.remaining_grams_est = 0
    s.updated_at = now

    # 解除所有激活绑定
    await db.execute(
        update(TrayMapping).where(TrayMapping.spool_id == spool_id, TrayMapping.unbound_at.is_(None)).values(unbound_at=now)
    )
    await db.commit()
    return {"ok": True}


@router.post("/{spool_id}/adjustments")
async def create_adjustment(spool_id: UUID, body: SpoolAdjustmentCreate, db: AsyncSession = Depends(get_db)) -> dict:
    s = await db.get(Spool, spool_id)
    if not s:
        raise HTTPException(status_code=404, detail="spool not found")

    adj = InventoryAdjustment(
        spool_id=spool_id,
        delta_grams=body.delta_grams,
        reason=body.reason,
        created_at=datetime.now(timezone.utc),
    )
    db.add(adj)
    await db.flush()
    await recalc_spool_remaining(db, spool_id)
    await db.commit()
    return {"ok": True, "adjustment_id": str(adj.id)}


@router.get("/{spool_id}/ledger", response_model=list[LedgerRow])
async def spool_ledger(spool_id: UUID, db: AsyncSession = Depends(get_db)) -> list[LedgerRow]:
    s = await db.get(Spool, spool_id)
    if not s:
        raise HTTPException(status_code=404, detail="spool not found")

    consumptions = (
        await db.execute(select(ConsumptionRecord).where(ConsumptionRecord.spool_id == spool_id))
    ).scalars().all()
    adjustments = (
        await db.execute(select(InventoryAdjustment).where(InventoryAdjustment.spool_id == spool_id))
    ).scalars().all()

    rows: list[LedgerRow] = []
    for c in consumptions:
        rows.append(
            LedgerRow(
                kind="consumption",
                at=c.created_at,
                grams=-int(c.grams),
                source=c.source,
                confidence=c.confidence,
                job_id=c.job_id,
            )
        )
    for a in adjustments:
        rows.append(
            LedgerRow(
                kind="adjustment",
                at=a.created_at,
                grams=int(a.delta_grams),
                note=a.reason,
            )
        )

    rows.sort(key=lambda r: r.at, reverse=True)
    return rows


