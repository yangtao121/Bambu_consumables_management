from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.material_ledger import MaterialLedger


async def get_total_trays(db: AsyncSession) -> int:
    total = await db.scalar(select(func.coalesce(func.sum(MaterialLedger.tray_delta), 0)))
    return int(total or 0)
