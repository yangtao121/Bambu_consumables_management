from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import settings
from app.core.crypto import encrypt_str
from app.db.models.printer import Printer
from app.db.models.normalized_event import NormalizedEvent
from app.schemas.printer import PrinterCreate, PrinterDetail, PrinterOut, PrinterUpdate


router = APIRouter(prefix="/printers", tags=["printers"])


@router.get("", response_model=list[PrinterOut])
async def list_printers(db: AsyncSession = Depends(get_db)) -> list[Printer]:
    return (await db.execute(select(Printer).order_by(Printer.created_at.desc()))).scalars().all()


@router.post("", response_model=PrinterDetail)
async def create_printer(body: PrinterCreate, db: AsyncSession = Depends(get_db)) -> Printer:
    p = Printer(
        ip=body.ip,
        serial=body.serial,
        alias=body.alias,
        model=body.model,
        lan_access_code_enc=encrypt_str(settings.app_secret_key, body.lan_access_code),
        status="unknown",
        last_seen=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(p)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="printer serial already exists")
    await db.refresh(p)
    return p


@router.get("/{printer_id}", response_model=PrinterDetail)
async def get_printer(printer_id: UUID, db: AsyncSession = Depends(get_db)) -> Printer:
    p = await db.get(Printer, printer_id)
    if not p:
        raise HTTPException(status_code=404, detail="printer not found")
    return p


@router.get("/{printer_id}/latest-report")
async def latest_report(printer_id: UUID, db: AsyncSession = Depends(get_db)) -> dict:
    p = await db.get(Printer, printer_id)
    if not p:
        raise HTTPException(status_code=404, detail="printer not found")

    ev = (
        await db.execute(
            select(NormalizedEvent)
            .where(NormalizedEvent.printer_id == printer_id)
            .order_by(NormalizedEvent.occurred_at.desc(), NormalizedEvent.id.desc())
            .limit(1)
        )
    ).scalars().first()

    return {"printer_id": str(printer_id), "event": ev.data_json if ev else None}


@router.patch("/{printer_id}", response_model=PrinterDetail)
async def update_printer(printer_id: UUID, body: PrinterUpdate, db: AsyncSession = Depends(get_db)) -> Printer:
    p = await db.get(Printer, printer_id)
    if not p:
        raise HTTPException(status_code=404, detail="printer not found")

    if body.ip is not None:
        p.ip = body.ip
    if body.alias is not None:
        p.alias = body.alias
    if body.model is not None:
        p.model = body.model
    if body.lan_access_code is not None:
        p.lan_access_code_enc = encrypt_str(settings.app_secret_key, body.lan_access_code)

    p.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(p)
    return p


@router.delete("/{printer_id}")
async def delete_printer(printer_id: UUID, db: AsyncSession = Depends(get_db)) -> dict:
    p = await db.get(Printer, printer_id)
    if not p:
        raise HTTPException(status_code=404, detail="printer not found")
    await db.delete(p)
    await db.commit()
    return {"ok": True}


