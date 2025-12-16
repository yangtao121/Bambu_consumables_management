from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AmsColorMapping(Base):
    __tablename__ = "ams_color_mappings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Canonicalized AMS color hex, e.g. "#FFFFFF"
    color_hex: Mapped[str] = mapped_column(Text, nullable=False)
    # Human-friendly name used as stock matching key, e.g. "白色"
    color_name: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


Index("ux_ams_color_mappings_hex", AmsColorMapping.color_hex, unique=True)

