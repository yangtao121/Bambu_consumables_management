from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.consumption_record import ConsumptionRecord
from app.db.models.inventory_adjustment import InventoryAdjustment
from app.db.models.spool import Spool


async def recalc_spool_remaining(session: AsyncSession, spool_id) -> int:
    initial = await session.scalar(select(Spool.initial_grams).where(Spool.id == spool_id))
    if initial is None:
        raise ValueError("spool not found")

    consumed = await session.scalar(
        select(func.coalesce(func.sum(ConsumptionRecord.grams), 0)).where(ConsumptionRecord.spool_id == spool_id)
    )
    adjusted = await session.scalar(
        select(func.coalesce(func.sum(InventoryAdjustment.delta_grams), 0)).where(InventoryAdjustment.spool_id == spool_id)
    )

    remaining = int(initial) + int(adjusted or 0) - int(consumed or 0)
    if remaining < 0:
        remaining = 0

    await session.execute(
        update(Spool).where(Spool.id == spool_id).values(remaining_grams_est=remaining)
    )
    return remaining


