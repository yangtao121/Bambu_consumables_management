from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import APIModel


class SpoolCreate(BaseModel):
    name: str
    material: str
    color: str
    brand: str | None = None
    diameter_mm: float = 1.75
    initial_grams: int = Field(ge=0)
    tare_grams: int | None = Field(default=None, ge=0)
    price_total: float | None = Field(default=None, ge=0)
    price_per_kg: float | None = Field(default=None, ge=0)
    purchase_date: date | None = None
    note: str | None = None


class SpoolUpdate(BaseModel):
    name: str | None = None
    material: str | None = None
    color: str | None = None
    brand: str | None = None
    diameter_mm: float | None = None
    tare_grams: int | None = Field(default=None, ge=0)
    price_total: float | None = Field(default=None, ge=0)
    price_per_kg: float | None = Field(default=None, ge=0)
    purchase_date: date | None = None
    note: str | None = None
    status: str | None = None


class SpoolOut(APIModel):
    id: UUID
    name: str
    material: str
    color: str
    brand: str | None
    diameter_mm: float
    initial_grams: int
    tare_grams: int | None
    price_total: float | None
    price_per_kg: float | None
    purchase_date: date | None
    note: str | None
    status: str
    remaining_grams_est: int
    created_at: datetime
    updated_at: datetime


class SpoolMarkEmpty(BaseModel):
    confirm: bool = True


class SpoolAdjustmentCreate(BaseModel):
    delta_grams: int
    reason: str | None = None


class LedgerRow(APIModel):
    kind: str  # consumption|adjustment
    at: datetime
    grams: int
    source: str | None = None
    confidence: str | None = None
    job_id: UUID | None = None
    note: str | None = None


