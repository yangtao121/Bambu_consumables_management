from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import APIModel


class PrinterCreate(BaseModel):
    ip: str
    serial: str
    lan_access_code: str = Field(min_length=1)
    alias: str | None = None
    model: str | None = None


class PrinterUpdate(BaseModel):
    ip: str | None = None
    alias: str | None = None
    model: str | None = None
    lan_access_code: str | None = None


class PrinterOut(APIModel):
    id: UUID
    ip: str
    serial: str
    alias: str | None
    model: str | None
    status: str
    last_seen: datetime | None


class PrinterDetail(PrinterOut):
    created_at: datetime
    updated_at: datetime


