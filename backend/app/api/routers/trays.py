from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.models.material_ledger import MaterialLedger


router = APIRouter(prefix="/trays", tags=["trays"])


class TrayDiscardCreate(BaseModel):
    count: int = Field(ge=1, description="Number of trays to discard (positive integer).")
    note: str | None = None


@router.get("/summary")
async def tray_summary(db: AsyncSession = Depends(get_db)) -> dict:
    total = await db.scalar(select(func.coalesce(func.sum(MaterialLedger.tray_delta), 0)))
    return {"total_trays": int(total or 0)}


@router.post("/discard")
async def discard_trays(body: TrayDiscardCreate, db: AsyncSession = Depends(get_db)) -> dict:
    n = int(body.count)
    if n <= 0:
        raise HTTPException(status_code=400, detail="count must be >= 1")

    now = datetime.now(timezone.utc)
    db.add(
        MaterialLedger(
            stock_id=None,
            job_id=None,
            delta_grams=0,
            tray_delta=-int(n),
            kind="tray_discard",
            reason=body.note or "discard trays",
            created_at=now,
        )
    )
    await db.commit()
    return {"ok": True, "discarded": int(n)}

