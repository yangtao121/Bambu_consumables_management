from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConsumptionRecord(Base):
    __tablename__ = "consumption_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("print_jobs.id", ondelete="CASCADE"), nullable=False)
    # legacy (spool-mode)
    spool_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("spools.id", ondelete="RESTRICT"), nullable=True)
    # new (stock-mode)
    stock_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("material_stocks.id", ondelete="RESTRICT"), nullable=True
    )
    tray_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    grams: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


Index("ix_consumption_records_job_id", ConsumptionRecord.job_id)
Index("ix_consumption_records_spool_id", ConsumptionRecord.spool_id)
Index("ix_consumption_records_stock_id", ConsumptionRecord.stock_id)
Index("ix_consumption_records_job_tray", ConsumptionRecord.job_id, ConsumptionRecord.tray_id)


