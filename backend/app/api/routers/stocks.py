from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.models.material_ledger import MaterialLedger
from app.db.models.material_stock import MaterialStock
from app.schemas.stock import StockAdjustmentCreate, StockCreate, StockLedgerRow, StockOut, StockUpdate
from app.services.stock_service import apply_stock_delta


router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("", response_model=list[StockOut])
async def list_stocks(
    material: str | None = Query(default=None),
    color: str | None = Query(default=None),
    brand: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[MaterialStock]:
    stmt = select(MaterialStock)
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

