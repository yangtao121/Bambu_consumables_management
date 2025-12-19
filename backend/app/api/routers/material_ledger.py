from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.models.material_ledger import MaterialLedger
from app.db.models.material_stock import MaterialStock
from app.schemas.stock import VoidRequest
from app.services.stock_service import apply_stock_delta

router = APIRouter(prefix="/material-ledger", tags=["material-ledger"])


@router.post("/{ledger_id}/reverse")
async def reverse_ledger_row(
    ledger_id: UUID,
    body: VoidRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Reverse a ledger row by writing a compensating ledger entry (no hard delete).

    Intended for system-generated adjustment rows that couldn't be "deleted" from UI.
    For safety, we only allow reversing `kind="adjustment"` rows.
    """
    r = await db.get(MaterialLedger, ledger_id)
    if not r:
        raise HTTPException(status_code=404, detail="ledger row not found")
    if getattr(r, "voided_at", None) is not None:
        raise HTTPException(status_code=409, detail="ledger row already voided")
    if (r.kind or "") != "adjustment":
        raise HTTPException(status_code=409, detail="only adjustment rows can be reversed")
    if r.stock_id is None:
        raise HTTPException(status_code=409, detail="ledger row has no stock_id")

    # Idempotency: if already reversed, do not reverse twice.
    already = await db.scalar(select(MaterialLedger.id).where(MaterialLedger.reversal_of_id == ledger_id))
    if already:
        return {"ok": True, "reversal_id": str(already)}

    st = await db.get(MaterialStock, r.stock_id)
    if not st:
        raise HTTPException(status_code=404, detail="stock not found")

    delta = int(getattr(r, "delta_grams") or 0)
    if delta == 0:
        raise HTTPException(status_code=409, detail="invalid ledger delta")
    # Safe reversal for positive deltas: cannot reverse grams already consumed.
    if delta > 0 and int(st.remaining_grams) < int(delta):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "cannot reverse: adjustment grams already consumed",
                "stock_remaining_grams": int(st.remaining_grams),
                "adjustment_grams": int(delta),
            },
        )

    now = datetime.now(timezone.utc)
    r.voided_at = now
    r.void_reason = body.reason

    s2 = await apply_stock_delta(
        db,
        r.stock_id,
        -int(delta),
        reason=f"reverse ledger={ledger_id} note={body.reason or ''}",
        job_id=None,
        kind="reversal",
        reversal_of_id=ledger_id,
    )
    # apply_stock_delta flushed; find the created row id via reversal_of_id
    rev_id = await db.scalar(select(MaterialLedger.id).where(MaterialLedger.reversal_of_id == ledger_id))
    await db.commit()
    return {"ok": True, "reversal_id": str(rev_id) if rev_id else None, "remaining_grams": int(s2.remaining_grams)}

