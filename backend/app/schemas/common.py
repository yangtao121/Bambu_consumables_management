from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class IdResponse(APIModel):
    id: UUID


class Health(APIModel):
    status: str
    time: datetime


