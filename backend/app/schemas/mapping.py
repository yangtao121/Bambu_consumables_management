from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import APIModel


class TrayMappingCreate(BaseModel):
    printer_id: UUID
    tray_id: int
    spool_id: UUID


class TrayMappingOut(APIModel):
    id: int
    printer_id: UUID
    tray_id: int
    spool_id: UUID
    bound_at: datetime
    unbound_at: datetime | None


