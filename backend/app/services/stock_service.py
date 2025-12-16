from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.material_ledger import MaterialLedger
from app.db.models.material_stock import MaterialStock


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def apply_stock_delta(
    session: AsyncSession,
    stock_id: UUID,
    delta_grams: int,
    reason: str | None = None,
    job_id: UUID | None = None,
) -> MaterialStock:
    s = await session.get(MaterialStock, stock_id)
    if not s:
        raise ValueError("stock not found")

    before = int(s.remaining_grams)
    target = before + int(delta_grams)
    after = max(0, target)
    effective_delta = after - before

    s.remaining_grams = int(after)
    s.updated_at = _utcnow()

    led = MaterialLedger(
        stock_id=stock_id,
        job_id=job_id,
        delta_grams=int(effective_delta),
        reason=reason,
        created_at=_utcnow(),
    )
    session.add(led)
    await session.flush()
    return s

