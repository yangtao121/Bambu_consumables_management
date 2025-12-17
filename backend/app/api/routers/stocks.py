from __future__ import annotations

from datetime import datetime, timezone
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Text, cast, func, literal_column, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.models.consumption_record import ConsumptionRecord
from app.db.models.material_ledger import MaterialLedger
from app.db.models.material_stock import MaterialStock
from app.db.models.print_job import PrintJob
from app.schemas.stock import (
    StockAdjustmentCreate,
    StockCreate,
    StockCreateResult,
    StockLedgerRow,
    StockLedgerUpdate,
    StockOut,
    StockUpdate,
)
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


@router.post("", response_model=StockCreateResult)
async def create_stock(body: StockCreate, db: AsyncSession = Depends(get_db)) -> StockCreateResult:
    """
    Create a new stock item keyed by (material, color, brand).
    If an active stock with the same key already exists, *merge* by adding remaining_grams.

    roll_weight_grams is only set on insert and is NOT updated on merge.
    """
    now = datetime.now(timezone.utc)
    delta_grams = int(body.remaining_grams or 0)

    # Optional purchase meta
    rolls_count = int(body.rolls_count) if body.rolls_count is not None else None
    has_tray = bool(body.has_tray) if body.has_tray is not None else None
    tray_delta = int(rolls_count or 0) if has_tray else 0

    tbl = MaterialStock.__table__
    ins = insert(tbl).values(
        id=uuid.uuid4(),
        material=body.material,
        color=body.color,
        brand=body.brand,
        roll_weight_grams=int(body.roll_weight_grams),
        remaining_grams=delta_grams,
        is_archived=False,
        archived_at=None,
        created_at=now,
        updated_at=now,
    )

    stmt = ins.on_conflict_do_update(
        index_elements=[tbl.c.material, tbl.c.color, tbl.c.brand],
        # Must match the partial unique index predicate exactly (see alembic 0004: "is_archived = false")
        index_where=(tbl.c.is_archived == False),  # noqa: E712
        set_={
            "remaining_grams": tbl.c.remaining_grams + ins.excluded.remaining_grams,
            "updated_at": now,
        },
    ).returning(
        *tbl.c,
        # PostgreSQL upsert trick: xmax == 0 => inserted, xmax != 0 => updated (merged)
        literal_column("xmax").label("_xmax"),
    )

    try:
        row = (await db.execute(stmt)).mappings().one()
        merged = bool(int(row.get("_xmax") or 0) != 0)

        # Ledger: record the delta added (skip if delta is 0 to reduce noise).
        if delta_grams != 0:
            db.add(
                MaterialLedger(
                    stock_id=row["id"],
                    job_id=None,
                    delta_grams=int(delta_grams),
                    reason="create+merge add via api" if merged else "create via api",
                    kind="purchase",
                    rolls_count=rolls_count,
                    price_per_roll=body.price_per_roll,
                    price_total=body.price_total,
                    has_tray=has_tray,
                    tray_delta=tray_delta,
                    created_at=now,
                )
            )

        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"create stock failed: {e}")

    # remaining_grams_after reflects the row state after merge/insert
    after = int(row.get("remaining_grams") or 0)
    # Build a response with nested stock payload expected by frontend
    stock = MaterialStock(**{k: v for k, v in row.items() if k in tbl.c.keys()})
    return StockCreateResult(
        stock=stock,
        merged=bool(merged),
        delta_grams=int(delta_grams),
        remaining_grams_after=int(after),
    )


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
        await apply_stock_delta(db, stock_id, int(body.delta_grams), reason=body.reason, job_id=None, kind="adjustment")
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
                id=r.id,
                at=r.created_at,
                grams=int(r.delta_grams),
                job_id=r.job_id,
                note=r.reason,
                rolls_count=r.rolls_count,
                price_per_roll=r.price_per_roll,
                price_total=r.price_total,
                has_tray=r.has_tray,
                tray_delta=r.tray_delta,
                kind=r.kind,
            )
        )
    return out


@router.patch("/{stock_id}/ledger/{ledger_id}", response_model=StockLedgerRow)
async def update_stock_ledger_row(
    stock_id: UUID,
    ledger_id: UUID,
    body: StockLedgerUpdate,
    db: AsyncSession = Depends(get_db),
) -> StockLedgerRow:
    if not await db.get(MaterialStock, stock_id):
        raise HTTPException(status_code=404, detail="stock not found")

    r = await db.get(MaterialLedger, ledger_id)
    if not r:
        raise HTTPException(status_code=404, detail="ledger row not found")
    if r.stock_id != stock_id:
        raise HTTPException(status_code=404, detail="ledger row not found for this stock")

    # Only allow editing purchase-like rows (manually created, not tied to a job).
    if r.job_id is not None or int(r.delta_grams) <= 0:
        raise HTTPException(status_code=409, detail="only purchase ledger rows can be edited")

    patch = body.model_dump(exclude_unset=True)
    if "note" in patch:
        r.reason = patch.pop("note")
    for k, v in patch.items():
        setattr(r, k, v)

    # Recompute tray_delta based on has_tray + rolls_count
    has_tray = bool(r.has_tray) if r.has_tray is not None else False
    rolls_count = int(r.rolls_count or 0)
    r.tray_delta = int(rolls_count) if has_tray else 0
    r.kind = r.kind or "purchase"

    await db.commit()
    await db.refresh(r)
    return StockLedgerRow(
        id=r.id,
        at=r.created_at,
        grams=int(r.delta_grams),
        job_id=r.job_id,
        note=r.reason,
        rolls_count=r.rolls_count,
        price_per_roll=r.price_per_roll,
        price_total=r.price_total,
        has_tray=r.has_tray,
        tray_delta=r.tray_delta,
        kind=r.kind,
    )

