from __future__ import annotations

from datetime import datetime, timedelta, timezone
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.models.consumption_record import ConsumptionRecord
from app.db.models.spool import Spool


router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/summary")
async def summary_report(
    days: int = Query(default=7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Dashboard 用：返回今日、近 N 天消耗汇总 + 近 N 天逐日趋势。
    """
    now = datetime.now(timezone.utc)
    today = now.date()
    start_date = today - timedelta(days=days - 1)
    start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    today_dt = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)

    unit_cost = func.coalesce(
        (Spool.price_per_kg / 1000.0),
        (Spool.price_total / func.nullif(Spool.initial_grams, 0)),
        0.0,
    )

    # 今日汇总
    today_stmt = (
        select(
            func.sum(ConsumptionRecord.grams).label("grams"),
            func.sum(ConsumptionRecord.grams * unit_cost).label("cost_est"),
        )
        .join(Spool, Spool.id == ConsumptionRecord.spool_id)
        .where(ConsumptionRecord.created_at >= today_dt)
    )
    today_row = (await db.execute(today_stmt)).first()

    # 近 N 天汇总
    last_stmt = (
        select(
            func.sum(ConsumptionRecord.grams).label("grams"),
            func.sum(ConsumptionRecord.grams * unit_cost).label("cost_est"),
        )
        .join(Spool, Spool.id == ConsumptionRecord.spool_id)
        .where(ConsumptionRecord.created_at >= start_dt)
    )
    last_row = (await db.execute(last_stmt)).first()

    # 逐日趋势
    day = func.date_trunc("day", ConsumptionRecord.created_at).label("day")
    daily_stmt = (
        select(
            day,
            func.sum(ConsumptionRecord.grams).label("grams"),
            func.sum(ConsumptionRecord.grams * unit_cost).label("cost_est"),
        )
        .join(Spool, Spool.id == ConsumptionRecord.spool_id)
        .where(ConsumptionRecord.created_at >= start_dt)
        .group_by(day)
        .order_by(day.asc())
    )
    daily_rows = (await db.execute(daily_stmt)).all()

    return {
        "days": days,
        "from_date": start_date.isoformat(),
        "to_date": today.isoformat(),
        "today": {
            "grams": int((today_row.grams if today_row else 0) or 0),
            "cost_est": float((today_row.cost_est if today_row else 0.0) or 0.0),
        },
        "last": {
            "grams": int((last_row.grams if last_row else 0) or 0),
            "cost_est": float((last_row.cost_est if last_row else 0.0) or 0.0),
        },
        "daily": [
            {
                "day": r.day.date().isoformat() if r.day is not None else None,
                "grams": int(r.grams or 0),
                "cost_est": float(r.cost_est or 0.0),
            }
            for r in daily_rows
        ],
    }


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


