from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.models.consumption_record import ConsumptionRecord
from app.db.models.material_ledger import MaterialLedger


router = APIRouter(prefix="/reports", tags=["reports"])


def _utc_day(dt: datetime) -> date:
    try:
        return dt.astimezone(timezone.utc).date()
    except Exception:
        return dt.date()


def _ledger_price_total(r: MaterialLedger) -> float | None:
    """
    Return total price for a purchase ledger row.
    Priority:
    - price_total
    - price_per_roll * rolls_count
    """
    if getattr(r, "price_total", None) is not None:
        try:
            return float(r.price_total)
        except Exception:
            return None
    if getattr(r, "price_per_roll", None) is not None and getattr(r, "rolls_count", None) is not None:
        try:
            return float(r.price_per_roll) * int(r.rolls_count)
        except Exception:
            return None
    return None


async def _compute_daily_cost(
    db: AsyncSession,
    *,
    start_date: date,
    end_date_exclusive: date,
) -> list[dict]:
    """
    Daily consumption grams + estimated cost using moving weighted average.

    Rules:
    - Only priced purchases contribute to priced balance (grams+cost).
    - Consumption cost is counted only for the portion covered by priced balance.
    - Total grams always include full consumption grams.
    """
    start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date_exclusive, datetime.min.time(), tzinfo=timezone.utc)

    # Build day buckets
    days: list[date] = []
    cur = start_date
    while cur < end_date_exclusive:
        days.append(cur)
        cur = cur + timedelta(days=1)
    buckets: dict[date, dict] = {
        d: {"day": d.isoformat(), "grams_total": 0, "cost_total": 0.0, "priced_grams": 0, "unpriced_grams": 0}
        for d in days
    }

    # Load all priced purchases and all consumptions up to end_dt (history needed for correct balance).
    purchase_rows = (
        await db.execute(
            select(MaterialLedger)
            .where(
                MaterialLedger.stock_id.is_not(None),
                MaterialLedger.delta_grams > 0,
                (MaterialLedger.price_total.is_not(None) | MaterialLedger.price_per_roll.is_not(None)),
                MaterialLedger.created_at < end_dt,
            )
            .order_by(MaterialLedger.created_at.asc(), MaterialLedger.id.asc())
        )
    ).scalars().all()

    consumption_rows = (
        await db.execute(
            select(ConsumptionRecord)
            .where(ConsumptionRecord.stock_id.is_not(None), ConsumptionRecord.created_at < end_dt)
            .order_by(ConsumptionRecord.created_at.asc(), ConsumptionRecord.id.asc())
        )
    ).scalars().all()

    # Merge events. If timestamp ties, process purchase before consumption.
    events: list[tuple[datetime, int, str, object]] = []
    for r in purchase_rows:
        events.append((r.created_at, 0, "purchase", r))
    for c in consumption_rows:
        events.append((c.created_at, 1, "consumption", c))
    events.sort(key=lambda x: (x[0], x[1]))

    # Balances per stock_id
    priced_balance_grams: dict[str, int] = {}
    priced_balance_cost: dict[str, float] = {}

    for at, _prio, kind, obj in events:
        if kind == "purchase":
            r: MaterialLedger = obj  # type: ignore[assignment]
            if r.stock_id is None:
                continue
            grams = int(getattr(r, "delta_grams") or 0)
            if grams <= 0:
                continue
            cost = _ledger_price_total(r)
            if cost is None:
                continue
            sid = str(r.stock_id)
            priced_balance_grams[sid] = int(priced_balance_grams.get(sid, 0) + grams)
            priced_balance_cost[sid] = float(priced_balance_cost.get(sid, 0.0) + float(cost))
            continue

        # consumption
        c: ConsumptionRecord = obj  # type: ignore[assignment]
        if c.stock_id is None:
            continue
        sid = str(c.stock_id)
        grams = int(getattr(c, "grams_effective", None) or getattr(c, "grams") or 0)
        if grams <= 0:
            continue

        bal_g = int(priced_balance_grams.get(sid, 0))
        bal_cost = float(priced_balance_cost.get(sid, 0.0))
        priced_used = min(int(grams), int(bal_g)) if bal_g > 0 else 0
        unit_cost = (bal_cost / bal_g) if (bal_g > 0 and bal_cost > 0.0) else 0.0
        cost = float(priced_used) * float(unit_cost) if priced_used > 0 else 0.0

        # Update balance (avoid negative from float drift)
        if priced_used > 0:
            priced_balance_grams[sid] = max(0, int(bal_g - priced_used))
            priced_balance_cost[sid] = max(0.0, float(bal_cost - cost))

        # Bucket only if within requested window
        if at >= start_dt:
            d = _utc_day(at)
            b = buckets.get(d)
            if b is not None:
                b["grams_total"] += int(grams)
                b["priced_grams"] += int(priced_used)
                b["unpriced_grams"] += int(grams - priced_used)
                b["cost_total"] += float(cost)

    # Finalize ordering and rounding
    out: list[dict] = []
    for d in days:
        b = buckets[d]
        out.append(
            {
                "day": b["day"],
                "grams_total": int(b["grams_total"]),
                "cost_total": float(round(float(b["cost_total"]), 2)),
                "priced_grams": int(b["priced_grams"]),
                "unpriced_grams": int(b["unpriced_grams"]),
            }
        )
    return out


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
    end_date_exclusive = today + timedelta(days=1)
    daily = await _compute_daily_cost(db, start_date=start_date, end_date_exclusive=end_date_exclusive)
    today_row = next((x for x in daily if x["day"] == today.isoformat()), None) or {
        "grams_total": 0,
        "cost_total": 0.0,
    }
    last_grams = sum(int(x["grams_total"]) for x in daily)
    last_cost = sum(float(x["cost_total"]) for x in daily)

    return {
        "days": days,
        "from_date": start_date.isoformat(),
        "to_date": today.isoformat(),
        "today": {
            "grams": int(today_row.get("grams_total") or 0),
            "cost_est": float(today_row.get("cost_total") or 0.0),
        },
        "last": {
            "grams": int(last_grams),
            "cost_est": float(round(float(last_cost), 2)),
        },
        "daily": [{"day": x["day"], "grams": x["grams_total"], "cost_est": x["cost_total"]} for x in daily],
    }


@router.get("/monthly")
async def monthly_report(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    # Compute monthly totals by grouping daily buckets (cost uses moving weighted average).
    now = datetime.now(timezone.utc)
    end_excl = (now.date() + timedelta(days=1)) if to_date is None else to_date
    if from_date is None:
        # Default: last 12 months window (keeps endpoint usable without heavy full-history scan).
        from_date_eff = (now.date().replace(day=1) - timedelta(days=365)).replace(day=1)
    else:
        from_date_eff = from_date

    daily = await _compute_daily_cost(db, start_date=from_date_eff, end_date_exclusive=end_excl)
    by_month: dict[str, dict] = {}
    for d in daily:
        m = d["day"][:7] + "-01"  # YYYY-MM-01
        it = by_month.get(m)
        if it is None:
            it = {"month": m, "grams": 0, "cost_est": 0.0}
            by_month[m] = it
        it["grams"] += int(d["grams_total"])
        it["cost_est"] += float(d["cost_total"])

    out: list[dict] = []
    for m in sorted(by_month.keys(), reverse=True):
        it = by_month[m]
        out.append(
            {
                "month": it["month"],
                "grams": int(it["grams"]),
                "cost_est": float(round(float(it["cost_est"]), 2)),
            }
        )
    return out


@router.get("/daily")
async def daily_report(
    days: int = Query(default=7, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> dict:
    now = datetime.now(timezone.utc)
    today = now.date()
    start_date = today - timedelta(days=days - 1)
    end_date_exclusive = today + timedelta(days=1)
    daily = await _compute_daily_cost(db, start_date=start_date, end_date_exclusive=end_date_exclusive)
    return {
        "days": days,
        "from_date": start_date.isoformat(),
        "to_date": today.isoformat(),
        "daily": daily,
    }


