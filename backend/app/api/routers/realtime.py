from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.models.normalized_event import NormalizedEvent
from app.db.models.printer import Printer


router = APIRouter(prefix="/realtime", tags=["realtime"])


def _sse(data: dict, event: str | None = None) -> str:
    lines = []
    if event:
        lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data, ensure_ascii=False)}")
    return "\n".join(lines) + "\n\n"


@router.get("/printers")
async def sse_printers(db: AsyncSession = Depends(get_db)) -> StreamingResponse:
    async def gen() -> AsyncIterator[str]:
        last: str | None = None
        while True:
            printers = (await db.execute(select(Printer).order_by(Printer.created_at.desc()))).scalars().all()
            payload = {
                "ts": datetime.utcnow().isoformat(),
                "printers": [
                    {
                        "id": str(p.id),
                        "ip": p.ip,
                        "serial": p.serial,
                        "alias": p.alias,
                        "model": p.model,
                        "status": p.status,
                        "last_seen": p.last_seen.isoformat() if p.last_seen else None,
                    }
                    for p in printers
                ],
            }
            s = json.dumps(payload, sort_keys=True, ensure_ascii=False)
            if s != last:
                last = s
                yield _sse(payload, event="printers")
            await asyncio.sleep(1.0)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/printers/{printer_id}")
async def sse_printer(printer_id: UUID, db: AsyncSession = Depends(get_db)) -> StreamingResponse:
    async def gen() -> AsyncIterator[str]:
        last_event_id: str | None = None
        while True:
            ev = (
                await db.execute(
                    select(NormalizedEvent)
                    .where(NormalizedEvent.printer_id == printer_id)
                    .order_by(NormalizedEvent.occurred_at.desc(), NormalizedEvent.id.desc())
                    .limit(1)
                )
            ).scalars().first()
            if ev and ev.event_id != last_event_id:
                last_event_id = ev.event_id
                yield _sse(
                    {
                        "printer_id": str(printer_id),
                        "type": ev.type,
                        "event_id": ev.event_id,
                        "occurred_at": ev.occurred_at.isoformat(),
                        "data": ev.data_json,
                    },
                    event="printer",
                )
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream")


