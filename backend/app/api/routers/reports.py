from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.models.consumption_record import ConsumptionRecord
from app.db.models.spool import Spool


router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/monthly")
async def monthly_report(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    # 仅做基础聚合：按月合计 grams，并估算成本（若能从 spool 算出单位成本）
    month = func.date_trunc("month", ConsumptionRecord.created_at).label("month")

    stmt = (
        select(
            month,
            func.sum(ConsumptionRecord.grams).label("grams"),
            func.sum(
                ConsumptionRecord.grams
                * func.coalesce(
                    (Spool.price_per_kg / 1000.0),
                    (Spool.price_total / func.nullif(Spool.initial_grams, 0)),
                    0.0,
                )
            ).label("cost_est"),
        )
        .join(Spool, Spool.id == ConsumptionRecord.spool_id)
        .group_by(month)
        .order_by(month.desc())
    )
    if from_date is not None:
        stmt = stmt.where(ConsumptionRecord.created_at >= from_date)
    if to_date is not None:
        stmt = stmt.where(ConsumptionRecord.created_at < to_date)

    rows = (await db.execute(stmt)).all()
    return [
        {
            "month": r.month.date().isoformat() if r.month is not None else None,
            "grams": int(r.grams or 0),
            "cost_est": float(r.cost_est or 0.0),
        }
        for r in rows
    ]


