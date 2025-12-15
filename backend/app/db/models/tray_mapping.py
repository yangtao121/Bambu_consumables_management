from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TrayMapping(Base):
    __tablename__ = "tray_mappings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    printer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("printers.id", ondelete="CASCADE"), nullable=False
    )
    tray_id: Mapped[int] = mapped_column(Integer, nullable=False)
    spool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spools.id", ondelete="RESTRICT"), nullable=False
    )

    bound_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    unbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


Index("ix_tray_mappings_printer_id_tray_id", TrayMapping.printer_id, TrayMapping.tray_id)
Index("ix_tray_mappings_spool_id", TrayMapping.spool_id)


