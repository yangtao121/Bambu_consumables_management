from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import APIModel


class StockCreate(BaseModel):
    material: str
    color: str
    brand: str

    roll_weight_grams: int = Field(default=1000, ge=1)
    rolls_count: int | None = Field(default=None, ge=0)
    remaining_grams: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_and_fill(self) -> "StockCreate":
        # If remaining_grams not provided, compute from rolls_count.
        if self.remaining_grams is None:
            if self.rolls_count is None:
                raise ValueError("remaining_grams 或 rolls_count 至少提供一个")
            self.remaining_grams = int(self.rolls_count) * int(self.roll_weight_grams)
        return self


class StockUpdate(BaseModel):
    material: str | None = None
    color: str | None = None
    brand: str | None = None
    roll_weight_grams: int | None = Field(default=None, ge=1)


class StockOut(APIModel):
    id: UUID
    material: str
    color: str
    brand: str
    roll_weight_grams: int
    remaining_grams: int
    is_archived: bool = False
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class StockAdjustmentCreate(BaseModel):
    delta_grams: int
    reason: str | None = None


class StockLedgerRow(APIModel):
    at: datetime
    grams: int
    job_id: UUID | None = None
    note: str | None = None

