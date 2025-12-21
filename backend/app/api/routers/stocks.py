from __future__ import annotations

from datetime import datetime, timezone
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Text, cast, func, literal_column, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.models.ams_color_mapping import AmsColorMapping
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
    StockManualConsumptionCreate,
    StockOut,
    StockUpdate,
    VoidRequest,
)
from app.services.pricing_service import (
    PricingConflict,
    derive_missing_price_per_roll,
    derive_missing_price_total,
    derive_purchase_prices,
)
from app.services.stock_service import apply_stock_delta
from app.services.tray_service import get_total_trays
from app.services.valuation_service import compute_stock_valuations


router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("", response_model=list[StockOut])
async def list_stocks(
    material: str | None = Query(default=None),
    color: str | None = Query(default=None),
    brand: str | None = Query(default=None),
    include_archived: bool = Query(default=False, description="Include archived (soft-deleted) stocks"),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    # 使用左连接查询库存和颜色映射
    stmt = (
        select(
            MaterialStock,
            AmsColorMapping.color_hex
        )
        .outerjoin(
            AmsColorMapping, 
            MaterialStock.color == AmsColorMapping.color_name
        )
    )
    
    if not include_archived:
        stmt = stmt.where(MaterialStock.is_archived.is_(False))
    if material:
        stmt = stmt.where(MaterialStock.material == material)
    if color:
        stmt = stmt.where(MaterialStock.color == color)
    if brand:
        stmt = stmt.where(MaterialStock.brand == brand)
    
    stmt = stmt.order_by(MaterialStock.updated_at.desc(), MaterialStock.created_at.desc())
    results = (await db.execute(stmt)).all()
    
    # 构建返回结果
    return [
        {
            "id": stock.id,
            "material": stock.material,
            "color": stock.color,
            "brand": stock.brand,
            "roll_weight_grams": stock.roll_weight_grams,
            "remaining_grams": stock.remaining_grams,
            "is_archived": stock.is_archived,
            "archived_at": stock.archived_at,
            "created_at": stock.created_at,
            "updated_at": stock.updated_at,
            "color_hex": color_hex  # 直接从连接查询获取
        }
        for stock, color_hex in results
    ]


@router.get("/valuations")
async def stock_valuations(
    include_archived: bool = Query(default=False, description="Include archived (soft-deleted) stocks"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Return valuations for stock list UI.

    - purchased_value_total:累计购入总价值（入库流水中可计价部分）
    - consumed_value_est:已消耗价值（按移动加权平均估算，仅计入已计价部分）
    - remaining_value_est:当前剩余价值（已计价余额）
    - consumed_rolls_est:已消耗卷数（估算，克数/单卷克数）
    """
    stmt = select(MaterialStock)
    if not include_archived:
        stmt = stmt.where(MaterialStock.is_archived.is_(False))
    stocks = (await db.execute(stmt)).scalars().all()
    ids = [s.id for s in stocks]
    vals = await compute_stock_valuations(db, stock_ids=ids)

    totals = {
        "purchased_value_total": 0.0,
        "consumed_value_est": 0.0,
        "remaining_value_est": 0.0,
        "consumed_rolls_est": 0.0,
    }
    by_stock_id: dict[str, dict] = {}
    for s in stocks:
        sid = str(s.id)
        v = vals.get(sid)
        if v is None:
            row = {
                "stock_id": sid,
                "purchased_value_total": 0.0,
                "consumed_value_est": 0.0,
                "remaining_value_est": 0.0,
                "consumed_grams_total": 0,
                "consumed_rolls_est": 0.0,
            }
        else:
            row = {
                "stock_id": v.stock_id,
                "purchased_value_total": float(v.purchased_value_total),
                "consumed_value_est": float(v.consumed_value_est),
                "remaining_value_est": float(v.remaining_value_est),
                "consumed_grams_total": int(v.consumed_grams_total),
                "consumed_rolls_est": float(v.consumed_rolls_est),
            }

        by_stock_id[sid] = row
        totals["purchased_value_total"] += float(row["purchased_value_total"])
        totals["consumed_value_est"] += float(row["consumed_value_est"])
        totals["remaining_value_est"] += float(row["remaining_value_est"])
        totals["consumed_rolls_est"] += float(row["consumed_rolls_est"])

    totals = {k: float(round(float(v), 2)) for k, v in totals.items()}
    return {
        "include_archived": bool(include_archived),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": totals,
        "by_stock_id": by_stock_id,
    }


@router.get("/{stock_id}/valuation")
async def stock_valuation(stock_id: UUID, db: AsyncSession = Depends(get_db)) -> dict:
    s = await db.get(MaterialStock, stock_id)
    if not s:
        raise HTTPException(status_code=404, detail="stock not found")
    vals = await compute_stock_valuations(db, stock_ids=[stock_id])
    v = vals.get(str(stock_id))
    if v is None:
        return {
            "stock_id": str(stock_id),
            "purchased_value_total": 0.0,
            "consumed_value_est": 0.0,
            "remaining_value_est": 0.0,
            "consumed_grams_total": 0,
            "consumed_rolls_est": 0.0,
        }
    return {
        "stock_id": v.stock_id,
        "purchased_value_total": float(v.purchased_value_total),
        "consumed_value_est": float(v.consumed_value_est),
        "remaining_value_est": float(v.remaining_value_est),
        "consumed_grams_total": int(v.consumed_grams_total),
        "consumed_rolls_est": float(v.consumed_rolls_est),
    }


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
    try:
        price_per_roll, price_total = derive_purchase_prices(
            rolls_count=rolls_count, price_per_roll=body.price_per_roll, price_total=body.price_total
        )
    except PricingConflict as e:
        raise HTTPException(status_code=409, detail={**e.detail, "message": e.message})

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
                    price_per_roll=price_per_roll,
                    price_total=price_total,
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
async def get_stock(stock_id: UUID, db: AsyncSession = Depends(get_db)) -> dict:
    s = await db.get(MaterialStock, stock_id)
    if not s:
        raise HTTPException(status_code=404, detail="stock not found")
    
    # 查询颜色映射
    color_mapping = (
        await db.execute(select(AmsColorMapping).where(AmsColorMapping.color_name == s.color))
    ).scalars().first()
    
    # 构建返回结果，添加color_hex字段
    return {
        "id": s.id,
        "material": s.material,
        "color": s.color,
        "brand": s.brand,
        "roll_weight_grams": s.roll_weight_grams,
        "remaining_grams": s.remaining_grams,
        "is_archived": s.is_archived,
        "archived_at": s.archived_at,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
        "color_hex": color_mapping.color_hex if color_mapping else None
    }


@router.patch("/{stock_id}", response_model=StockOut)
async def update_stock(
    stock_id: UUID,
    body: StockUpdate,
    merge: bool = Query(default=False, description="If key conflicts, merge remaining grams into existing active stock"),
    db: AsyncSession = Depends(get_db),
) -> MaterialStock:
    s = await db.get(MaterialStock, stock_id)
    if not s:
        raise HTTPException(status_code=404, detail="stock not found")

    patch = body.model_dump(exclude_unset=True)
    now = datetime.now(timezone.utc)

    # Detect potential key change (material+color+brand)
    new_material = patch.get("material", s.material)
    new_color = patch.get("color", s.color)
    new_brand = patch.get("brand", s.brand)
    key_changed = (new_material, new_color, new_brand) != (s.material, s.color, s.brand)

    if key_changed:
        # If a different active stock already owns the target key, optionally merge into it.
        target = (
            await db.execute(
                select(MaterialStock).where(
                    MaterialStock.material == new_material,
                    MaterialStock.color == new_color,
                    MaterialStock.brand == new_brand,
                    MaterialStock.is_archived.is_(False),
                    MaterialStock.id != stock_id,
                )
            )
        ).scalars().first()

        if target is not None and merge:
            grams_to_move = int(getattr(s, "remaining_grams") or 0)
            if grams_to_move > 0:
                await apply_stock_delta(
                    db,
                    target.id,
                    +int(grams_to_move),
                    reason=f"merge_in from={stock_id}",
                    job_id=None,
                    kind="merge_in",
                )
                await apply_stock_delta(
                    db,
                    s.id,
                    -int(grams_to_move),
                    reason=f"merge_out to={target.id}",
                    job_id=None,
                    kind="merge_out",
                )

            # Optional: allow changing roll weight as part of the merge action (applies to target)
            if "roll_weight_grams" in patch and patch["roll_weight_grams"] is not None:
                target.roll_weight_grams = int(patch["roll_weight_grams"])
                target.updated_at = now

            # Archive source stock after merging remaining grams
            s.is_archived = True
            s.archived_at = now
            s.updated_at = now

            await db.commit()
            await db.refresh(target)
            return target

        # No merge (or no conflict target): attempt in-place update; on conflict, surface 409 with target info.
        for k, v in patch.items():
            setattr(s, k, v)
        s.updated_at = now
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            conflict = (
                await db.execute(
                    select(MaterialStock).where(
                        MaterialStock.material == new_material,
                        MaterialStock.color == new_color,
                        MaterialStock.brand == new_brand,
                        MaterialStock.is_archived.is_(False),
                    )
                )
            ).scalars().first()
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "stock key conflict",
                    "conflict_stock_id": str(conflict.id) if conflict else None,
                    "key": {"material": new_material, "color": new_color, "brand": new_brand},
                },
            )

        await db.refresh(s)
        return s

    # No key change: normal patch
    for k, v in patch.items():
        setattr(s, k, v)
    s.updated_at = now
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


@router.post("/{stock_id}/restore")
async def restore_stock(
    stock_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    s = await db.get(MaterialStock, stock_id)
    if not s:
        raise HTTPException(status_code=404, detail="stock not found")
    
    # Not archived: nothing to do
    if not getattr(s, "is_archived", False):
        return {"ok": True, "already_restored": True}
    
    # Check if there's a conflict with existing active stock
    existing_stock = (
        await db.execute(
            select(MaterialStock).where(
                MaterialStock.material == s.material,
                MaterialStock.color == s.color,
                MaterialStock.brand == s.brand,
                MaterialStock.is_archived.is_(False),
                MaterialStock.id != stock_id,
            )
        )
    ).scalars().first()
    
    if existing_stock:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "stock key conflict with existing active stock",
                "conflict_stock_id": str(existing_stock.id),
                "key": {"material": s.material, "color": s.color, "brand": s.brand},
            },
        )
    
    # Restore the stock
    now = datetime.now(timezone.utc)
    s.is_archived = False
    s.archived_at = None
    s.updated_at = now
    await db.commit()
    return {"ok": True, "restored": True}


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
        # Backward compatible display: if only one side exists, derive the other in response (do not write back).
        derived_total = derive_missing_price_total(
            rolls_count=r.rolls_count, price_per_roll=r.price_per_roll, price_total=r.price_total
        )
        derived_ppr = derive_missing_price_per_roll(
            rolls_count=r.rolls_count, price_per_roll=r.price_per_roll, price_total=r.price_total
        )
        out.append(
            StockLedgerRow(
                id=r.id,
                at=r.created_at,
                grams=int(r.delta_grams),
                job_id=r.job_id,
                note=r.reason,
                voided_at=getattr(r, "voided_at", None),
                void_reason=getattr(r, "void_reason", None),
                reversal_of_id=getattr(r, "reversal_of_id", None),
                rolls_count=r.rolls_count,
                price_per_roll=derived_ppr,
                price_total=derived_total,
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

    total_trays = await get_total_trays(db)
    if total_trays < 0:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "total trays is negative; tray mutations are temporarily blocked until fixed",
                "total_trays": int(total_trays),
            },
        )

    r = await db.get(MaterialLedger, ledger_id)
    if not r:
        raise HTTPException(status_code=404, detail="ledger row not found")
    if r.stock_id != stock_id:
        raise HTTPException(status_code=404, detail="ledger row not found for this stock")

    # Only allow editing purchase-like rows (manually created, not tied to a job).
    if r.job_id is not None or int(r.delta_grams) <= 0:
        raise HTTPException(status_code=409, detail="only purchase ledger rows can be edited")

    patch = body.model_dump(exclude_unset=True)

    # Predict tray_delta change (global trays cannot go negative)
    old_tray_delta = int(r.tray_delta or 0)
    prospective_has_tray = patch.get("has_tray", r.has_tray)
    prospective_rolls_count = patch.get("rolls_count", r.rolls_count)
    has_tray_true = bool(prospective_has_tray) if prospective_has_tray is not None else False
    rolls_count = int(prospective_rolls_count or 0)
    new_tray_delta = int(rolls_count) if has_tray_true else 0
    tray_change = int(new_tray_delta) - int(old_tray_delta)
    if int(total_trays) + int(tray_change) < 0:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "total trays cannot be negative",
                "total_trays": int(total_trays),
                "old_tray_delta": int(old_tray_delta),
                "new_tray_delta": int(new_tray_delta),
                "tray_change": int(tray_change),
                "new_total": int(int(total_trays) + int(tray_change)),
            },
        )

    if "note" in patch:
        r.reason = patch.pop("note")
    for k, v in patch.items():
        setattr(r, k, v)

    # Apply predicted tray_delta based on has_tray + rolls_count
    r.tray_delta = int(new_tray_delta)
    r.kind = r.kind or "purchase"

    # Pricing: derive missing fields + enforce consistency.
    try:
        price_per_roll, price_total = derive_purchase_prices(
            rolls_count=r.rolls_count, price_per_roll=r.price_per_roll, price_total=r.price_total
        )
        r.price_per_roll = price_per_roll
        r.price_total = price_total
    except PricingConflict as e:
        raise HTTPException(status_code=409, detail={**e.detail, "message": e.message})

    await db.commit()
    await db.refresh(r)
    return StockLedgerRow(
        id=r.id,
        at=r.created_at,
        grams=int(r.delta_grams),
        job_id=r.job_id,
        note=r.reason,
        voided_at=getattr(r, "voided_at", None),
        void_reason=getattr(r, "void_reason", None),
        reversal_of_id=getattr(r, "reversal_of_id", None),
        rolls_count=r.rolls_count,
        price_per_roll=derive_missing_price_per_roll(
            rolls_count=r.rolls_count, price_per_roll=r.price_per_roll, price_total=r.price_total
        ),
        price_total=derive_missing_price_total(
            rolls_count=r.rolls_count, price_per_roll=r.price_per_roll, price_total=r.price_total
        ),
        has_tray=r.has_tray,
        tray_delta=r.tray_delta,
        kind=r.kind,
    )


@router.post("/{stock_id}/consumptions")
async def add_manual_stock_consumption(
    stock_id: UUID,
    body: StockManualConsumptionCreate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    st = await db.get(MaterialStock, stock_id)
    if not st:
        raise HTTPException(status_code=404, detail="stock not found")

    grams_requested = int(body.grams)
    grams_effective = min(int(grams_requested), int(st.remaining_grams))
    if grams_effective <= 0:
        raise HTTPException(status_code=409, detail="stock has no remaining grams")

    c = ConsumptionRecord(
        job_id=None,
        spool_id=None,
        stock_id=stock_id,
        tray_id=None,
        segment_idx=None,
        grams=int(grams_effective),
        grams_requested=int(grams_requested),
        grams_effective=int(grams_effective),
        source="manual_stock",
        confidence="high",
        created_at=datetime.now(timezone.utc),
    )
    db.add(c)
    await db.flush()

    await apply_stock_delta(
        db,
        stock_id,
        -int(grams_effective),
        reason=f"manual_stock consumption={c.id} note={body.note or ''}",
        job_id=None,
        kind="consumption",
    )
    await db.commit()
    return {"ok": True, "consumption_id": str(c.id), "note": body.note}


@router.post("/{stock_id}/consumptions/{consumption_id}/void")
async def void_stock_consumption(
    stock_id: UUID,
    consumption_id: UUID,
    body: VoidRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    st = await db.get(MaterialStock, stock_id)
    if not st:
        raise HTTPException(status_code=404, detail="stock not found")

    c = await db.get(ConsumptionRecord, consumption_id)
    if not c or c.stock_id != stock_id:
        raise HTTPException(status_code=404, detail="consumption not found")
    if getattr(c, "voided_at", None) is not None:
        raise HTTPException(status_code=409, detail="consumption already voided")

    grams = int(getattr(c, "grams_effective", None) or getattr(c, "grams") or 0)
    if grams <= 0:
        raise HTTPException(status_code=409, detail="invalid consumption grams")

    now = datetime.now(timezone.utc)
    c.voided_at = now
    c.void_reason = body.reason

    await apply_stock_delta(
        db,
        stock_id,
        +int(grams),
        reason=f"void consumption={consumption_id} source={c.source} note={body.reason or ''}",
        job_id=None,
        kind="reversal",
    )
    await db.commit()
    return {"ok": True}


@router.post("/{stock_id}/ledger/{ledger_id}/void")
async def void_stock_ledger_row(
    stock_id: UUID,
    ledger_id: UUID,
    body: VoidRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    st = await db.get(MaterialStock, stock_id)
    if not st:
        raise HTTPException(status_code=404, detail="stock not found")

    r = await db.get(MaterialLedger, ledger_id)
    if not r or r.stock_id != stock_id:
        raise HTTPException(status_code=404, detail="ledger row not found")
    if getattr(r, "voided_at", None) is not None:
        raise HTTPException(status_code=409, detail="ledger row already voided")

    if r.job_id is not None or (r.kind or "") != "adjustment":
        raise HTTPException(status_code=409, detail="only manual adjustment rows can be voided")

    delta = int(r.delta_grams or 0)
    if delta == 0:
        raise HTTPException(status_code=409, detail="invalid ledger delta")
    # Safe reversal for positive deltas: cannot reverse grams already consumed.
    if delta > 0 and int(st.remaining_grams) < int(delta):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "cannot void: adjustment grams already consumed",
                "stock_remaining_grams": int(st.remaining_grams),
                "adjustment_grams": int(delta),
            },
        )

    now = datetime.now(timezone.utc)
    r.voided_at = now
    r.void_reason = body.reason

    await apply_stock_delta(
        db,
        stock_id,
        -int(delta),
        reason=f"void ledger={ledger_id} note={body.reason or ''}",
        job_id=None,
        kind="reversal",
        reversal_of_id=ledger_id,
    )
    await db.commit()
    return {"ok": True}


@router.post("/{stock_id}/bind-color")
async def bind_color_to_stock(
    stock_id: UUID,
    color_hex: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    将颜色码绑定到库存项
    
    如果颜色码已存在映射，则直接使用
    如果颜色码不存在，则创建新的映射
    """
    from app.schemas.color_mapping import normalize_color_hex
    
    # 验证库存项存在
    stock = await db.get(MaterialStock, stock_id)
    if not stock:
        raise HTTPException(status_code=404, detail="stock not found")
    
    # 标准化颜色码格式
    try:
        normalized_hex = normalize_color_hex(color_hex)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid color hex: {str(e)}")
    
    # 查找现有颜色映射
    existing_mapping = (
        await db.execute(select(AmsColorMapping).where(AmsColorMapping.color_hex == normalized_hex))
    ).scalars().first()
    
    if not existing_mapping:
        # 创建新的颜色映射
        now = datetime.now(timezone.utc)
        new_mapping = AmsColorMapping(
            color_hex=normalized_hex,
            color_name=stock.color,  # 使用库存项的颜色名称
            created_at=now,
            updated_at=now
        )
        db.add(new_mapping)
        try:
            await db.commit()
        except Exception as e:
            await db.rollback()
            raise HTTPException(status_code=400, detail=f"Failed to create color mapping: {str(e)}")
        await db.refresh(new_mapping)
    else:
        # 检查颜色名称是否匹配，如果不匹配，更新颜色名称
        if existing_mapping.color_name != stock.color:
            existing_mapping.color_name = stock.color
            existing_mapping.updated_at = datetime.now(timezone.utc)
            try:
                await db.commit()
            except Exception as e:
                await db.rollback()
                raise HTTPException(status_code=400, detail=f"Failed to update color mapping: {str(e)}")
    
    return {
        "ok": True,
        "stock_id": str(stock_id),
        "color_hex": normalized_hex,
        "color_name": stock.color,
        "message": "颜色绑定成功"
    }

