from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import APIModel


class JobOut(APIModel):
    id: UUID
    printer_id: UUID
    job_key: str | None
    file_name: str | None
    status: str
    started_at: datetime
    ended_at: datetime | None
    spool_binding_snapshot_json: dict
    created_at: datetime
    updated_at: datetime


class ManualConsumptionCreate(BaseModel):
    spool_id: UUID
    grams: int = Field(ge=0)
    note: str | None = None


