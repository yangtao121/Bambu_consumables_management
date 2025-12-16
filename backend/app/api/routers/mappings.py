from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.models.printer import Printer
from app.db.models.spool import Spool
from app.db.models.tray_mapping import TrayMapping
from app.schemas.mapping import TrayMappingCreate, TrayMappingOut, TrayMappingUnbind


router = APIRouter(prefix="/tray-mappings", tags=["tray-mappings"])


@router.get("", response_model=list[TrayMappingOut])
async def list_mappings(
    printer_id: UUID | None = Query(default=None),
    active_only: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
) -> list[TrayMapping]:
    stmt = select(TrayMapping)
    if printer_id is not None:
        stmt = stmt.where(TrayMapping.printer_id == printer_id)
    if active_only:
        stmt = stmt.where(TrayMapping.unbound_at.is_(None))
    stmt = stmt.order_by(TrayMapping.bound_at.desc())
    return (await db.execute(stmt)).scalars().all()


@router.post("", response_model=TrayMappingOut)
async def bind_mapping(body: TrayMappingCreate, db: AsyncSession = Depends(get_db)) -> TrayMapping:
    if not await db.get(Printer, body.printer_id):
        raise HTTPException(status_code=404, detail="printer not found")
    if not await db.get(Spool, body.spool_id):
        raise HTTPException(status_code=404, detail="spool not found")

    now = datetime.now(timezone.utc)
    # 先解绑同一 printer/tray 的激活记录（确保 partial unique）
    await db.execute(
        update(TrayMapping)
        .where(
            TrayMapping.printer_id == body.printer_id,
            TrayMapping.tray_id == body.tray_id,
            TrayMapping.unbound_at.is_(None),
        )
        .values(unbound_at=now)
    )

    m = TrayMapping(printer_id=body.printer_id, tray_id=body.tray_id, spool_id=body.spool_id, bound_at=now, unbound_at=None)
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return m


@router.post("/unbind")
async def unbind_mapping(body: TrayMappingUnbind, db: AsyncSession = Depends(get_db)) -> dict:
    # 幂等：若不存在激活绑定，仍返回 ok
    if not await db.get(Printer, body.printer_id):
        raise HTTPException(status_code=404, detail="printer not found")

    now = datetime.now(timezone.utc)
    await db.execute(
        update(TrayMapping)
        .where(
            TrayMapping.printer_id == body.printer_id,
            TrayMapping.tray_id == body.tray_id,
            TrayMapping.unbound_at.is_(None),
        )
        .values(unbound_at=now)
    )
    await db.commit()
    return {"ok": True}

