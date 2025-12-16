from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Text, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.models.consumption_record import ConsumptionRecord
from app.db.models.material_ledger import MaterialLedger
from app.db.models.material_stock import MaterialStock
from app.db.models.print_job import PrintJob
from app.schemas.stock import StockAdjustmentCreate, StockCreate, StockLedgerRow, StockOut, StockUpdate
from app.services.stock_service import apply_stock_delta


router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("", response_model=list[StockOut])
async def list_stocks(
    material: str | None = Query(default=None),
    color: str | None = Query(default=None),
    brand: str | None = Query(default=None),
    include_archived: bool = Query(default=False, description="Include archived (soft-deleted) stocks"),
    db: AsyncSession = Depends(get_db),
) -> list[MaterialStock]:
    stmt = select(MaterialStock)
    if not include_archived:
        stmt = stmt.where(MaterialStock.is_archived.is_(False))
    if material:
        stmt = stmt.where(MaterialStock.material == material)
    if color:
        stmt = stmt.where(MaterialStock.color == color)
    if brand:
        stmt = stmt.where(MaterialStock.brand == brand)
    stmt = stmt.order_by(MaterialStock.updated_at.desc(), MaterialStock.created_at.desc())
    return (await db.execute(stmt)).scalars().all()


@router.post("", response_model=StockOut)
async def create_stock(body: StockCreate, db: AsyncSession = Depends(get_db)) -> MaterialStock:
    now = datetime.now(timezone.utc)
    s = MaterialStock(
        material=body.material,
        color=body.color,
        brand=body.brand,
        roll_weight_grams=int(body.roll_weight_grams),
        remaining_grams=int(body.remaining_grams or 0),
        created_at=now,
        updated_at=now,
    )
    db.add(s)
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"create stock failed: {e}")
    await db.refresh(s)
    return s


@router.get("/{stock_id}", response_model=StockOut)
async def get_stock(stock_id: UUID, db: AsyncSession = Depends(get_db)) -> MaterialStock:
    s = await db.get(MaterialStock, stock_id)
    if not s:
        raise HTTPException(status_code=404, detail="stock not found")
    return s


@router.patch("/{stock_id}", response_model=StockOut)
async def update_stock(stock_id: UUID, body: StockUpdate, db: AsyncSession = Depends(get_db)) -> MaterialStock:
    s = await db.get(MaterialStock, stock_id)
    if not s:
        raise HTTPException(status_code=404, detail="stock not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    s.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(s)
    return s


@router.delete("/{stock_id}")
async def archive_stock(
    stock_id: UUID,
    force: bool = Query(default=False, description="Force archive even if referenced by history"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    s = await db.get(MaterialStock, stock_id)
    if not s:
        raise HTTPException(status_code=404, detail="stock not found")

    # Already archived: idempotent
    if getattr(s, "is_archived", False):
        return {"ok": True, "already_archived": True}

    consumption_count = int(
        (await db.scalar(select(func.count()).select_from(ConsumptionRecord).where(ConsumptionRecord.stock_id == stock_id)))
        or 0
    )
    # Best-effort snapshot reference count (JSONB contains stock_id string)
    stock_id_str = str(stock_id)
    job_count = int(
        (
            await db.scalar(
                select(func.count())
                .select_from(PrintJob)
                .where(cast(PrintJob.spool_binding_snapshot_json, Text).like(f"%{stock_id_str}%"))
            )
        )
        or 0
    )

    if (consumption_count > 0 or job_count > 0) and not force:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "stock is referenced by history",
                "consumption_count": consumption_count,
                "job_count": job_count,
            },
        )

    now = datetime.now(timezone.utc)
    s.is_archived = True
    s.archived_at = now
    s.updated_at = now
    await db.commit()
    return {"ok": True, "archived": True, "consumption_count": consumption_count, "job_count": job_count}


@router.post("/{stock_id}/adjustments")
async def create_adjustment(stock_id: UUID, body: StockAdjustmentCreate, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        await apply_stock_delta(db, stock_id, int(body.delta_grams), reason=body.reason, job_id=None)
        await db.commit()
        return {"ok": True}
    except ValueError:
        await db.rollback()
        raise HTTPException(status_code=404, detail="stock not found")


@router.get("/{stock_id}/ledger", response_model=list[StockLedgerRow])
async def stock_ledger(stock_id: UUID, db: AsyncSession = Depends(get_db)) -> list[StockLedgerRow]:
    if not await db.get(MaterialStock, stock_id):
        raise HTTPException(status_code=404, detail="stock not found")
    rows = (
        await db.execute(select(MaterialLedger).where(MaterialLedger.stock_id == stock_id).order_by(MaterialLedger.created_at.desc()))
    ).scalars().all()
    out: list[StockLedgerRow] = []
    for r in rows:
        out.append(
            StockLedgerRow(
                at=r.created_at,
                grams=int(r.delta_grams),
                job_id=r.job_id,
                note=r.reason,
            )
        )
    return out

