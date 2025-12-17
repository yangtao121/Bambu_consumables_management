from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.consumption_record import ConsumptionRecord
from app.db.models.material_ledger import MaterialLedger
from app.db.models.material_stock import MaterialStock
from app.services.pricing_service import derive_missing_price_total


@dataclass
class StockValuation:
    stock_id: str
    roll_weight_grams: int
    remaining_grams: int
    purchased_value_total: float
    consumed_grams_total: int
    consumed_value_est: float
    remaining_value_est: float
    consumed_rolls_est: float


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _round2(v: float) -> float:
    return float(round(float(v), 2))


async def compute_stock_valuations(
    db: AsyncSession,
    *,
    stock_ids: list[UUID],
) -> dict[str, StockValuation]:
    """
    Compute valuations per stock using moving weighted average, similar to reports cost logic.

    Outputs:
    - purchased_value_total: sum of priced purchase ledger totals
    - consumed_value_est: estimated consumption cost (priced portion only)
    - remaining_value_est: remaining priced balance cost
    - consumed_rolls_est: consumed_grams_total / roll_weight_grams (2 decimals)
    """
    if not stock_ids:
        return {}

    stocks = (
        await db.execute(select(MaterialStock).where(MaterialStock.id.in_(stock_ids)))
    ).scalars().all()
    stock_meta: dict[str, MaterialStock] = {str(s.id): s for s in stocks}

    # Load all priced purchases + all consumption records for these stock ids
    purchase_rows = (
        await db.execute(
            select(MaterialLedger)
            .where(
                MaterialLedger.stock_id.in_(stock_ids),
                MaterialLedger.delta_grams > 0,
                (MaterialLedger.price_total.is_not(None) | MaterialLedger.price_per_roll.is_not(None)),
            )
            .order_by(MaterialLedger.created_at.asc(), MaterialLedger.id.asc())
        )
    ).scalars().all()

    consumption_rows = (
        await db.execute(
            select(ConsumptionRecord)
            .where(ConsumptionRecord.stock_id.in_(stock_ids), ConsumptionRecord.voided_at.is_(None))
            .order_by(ConsumptionRecord.created_at.asc(), ConsumptionRecord.id.asc())
        )
    ).scalars().all()

    # Merge: purchase before consumption when tie
    events: list[tuple[datetime, int, str, object]] = []
    for r in purchase_rows:
        events.append((r.created_at, 0, "purchase", r))
    for c in consumption_rows:
        events.append((c.created_at, 1, "consumption", c))
    events.sort(key=lambda x: (x[0], x[1]))

    # Running balances
    bal_g: dict[str, int] = {sid: 0 for sid in stock_meta.keys()}
    bal_cost: dict[str, float] = {sid: 0.0 for sid in stock_meta.keys()}

    purchased_total: dict[str, float] = {sid: 0.0 for sid in stock_meta.keys()}
    consumed_g_total: dict[str, int] = {sid: 0 for sid in stock_meta.keys()}
    consumed_cost_total: dict[str, float] = {sid: 0.0 for sid in stock_meta.keys()}

    for _at, _prio, kind, obj in events:
        if kind == "purchase":
            r: MaterialLedger = obj  # type: ignore[assignment]
            if r.stock_id is None:
                continue
            sid = str(r.stock_id)
            if sid not in stock_meta:
                continue
            grams = int(getattr(r, "delta_grams") or 0)
            if grams <= 0:
                continue
            cost_total = derive_missing_price_total(
                rolls_count=r.rolls_count, price_per_roll=r.price_per_roll, price_total=r.price_total
            )
            if cost_total is None:
                continue
            purchased_total[sid] = float(purchased_total.get(sid, 0.0) + float(cost_total))
            bal_g[sid] = int(bal_g.get(sid, 0) + grams)
            bal_cost[sid] = float(bal_cost.get(sid, 0.0) + float(cost_total))
            continue

        c: ConsumptionRecord = obj  # type: ignore[assignment]
        if c.stock_id is None:
            continue
        sid = str(c.stock_id)
        if sid not in stock_meta:
            continue
        grams = int(getattr(c, "grams_effective", None) or getattr(c, "grams") or 0)
        if grams <= 0:
            continue

        consumed_g_total[sid] = int(consumed_g_total.get(sid, 0) + grams)
        bg = int(bal_g.get(sid, 0))
        bc = float(bal_cost.get(sid, 0.0))
        priced_used = min(int(grams), int(bg)) if bg > 0 else 0
        unit_cost = (bc / bg) if (bg > 0 and bc > 0.0) else 0.0
        cost = float(priced_used) * float(unit_cost) if priced_used > 0 else 0.0
        consumed_cost_total[sid] = float(consumed_cost_total.get(sid, 0.0) + float(cost))

        if priced_used > 0:
            bal_g[sid] = max(0, int(bg - priced_used))
            bal_cost[sid] = max(0.0, float(bc - cost))

    out: dict[str, StockValuation] = {}
    for sid, s in stock_meta.items():
        roll_w = int(getattr(s, "roll_weight_grams") or 0) or 0
        cons_g = int(consumed_g_total.get(sid, 0))
        cons_rolls = 0.0
        try:
            if roll_w > 0:
                cons_rolls = float(Decimal(cons_g) / Decimal(roll_w))
        except Exception:
            cons_rolls = 0.0
        out[sid] = StockValuation(
            stock_id=sid,
            roll_weight_grams=roll_w,
            remaining_grams=int(getattr(s, "remaining_grams") or 0),
            purchased_value_total=_round2(float(purchased_total.get(sid, 0.0))),
            consumed_grams_total=cons_g,
            consumed_value_est=_round2(float(consumed_cost_total.get(sid, 0.0))),
            remaining_value_est=_round2(float(bal_cost.get(sid, 0.0))),
            consumed_rolls_est=_round2(float(cons_rolls)),
        )
    return out

