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
    stock_id: UUID
    grams: int = Field(ge=0)
    note: str | None = None


class ManualConsumptionVoid(BaseModel):
    reason: str | None = None


class JobConsumptionOut(APIModel):
    id: UUID
    job_id: UUID | None = None
    tray_id: int | None = None
    stock_id: UUID | None = None
    material: str | None = None
    color: str | None = None
    brand: str | None = None

    # legacy fields (spool-mode)
    spool_id: UUID | None = None
    spool_name: str | None = None
    spool_material: str | None = None
    spool_color: str | None = None

    grams: int
    source: str
    confidence: str
    created_at: datetime
    voided_at: datetime | None = None
    void_reason: str | None = None


class JobMaterialResolveItem(BaseModel):
    tray_id: int
    stock_id: UUID


class JobMaterialResolve(BaseModel):
    items: list[JobMaterialResolveItem] = Field(default_factory=list)

