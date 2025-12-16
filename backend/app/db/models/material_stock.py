from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MaterialStock(Base):
    __tablename__ = "material_stocks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    material: Mapped[str] = mapped_column(Text, nullable=False)
    color: Mapped[str] = mapped_column(Text, nullable=False)
    brand: Mapped[str] = mapped_column(Text, nullable=False)

    roll_weight_grams: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    remaining_grams: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Soft-delete / archive
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


Index(
    "ux_material_stocks_key_active",
    MaterialStock.material,
    MaterialStock.color,
    MaterialStock.brand,
    unique=True,
    postgresql_where=MaterialStock.is_archived.is_(False),
)
