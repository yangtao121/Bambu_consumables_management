from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConsumptionRecord(Base):
    __tablename__ = "consumption_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # job_id is nullable to support manual stock consumptions not tied to a job
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("print_jobs.id", ondelete="CASCADE"), nullable=True
    )
    # legacy (spool-mode)
    spool_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("spools.id", ondelete="RESTRICT"), nullable=True)
    # new (stock-mode)
    stock_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("material_stocks.id", ondelete="RESTRICT"), nullable=True
    )
    tray_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Segment index per (job_id, tray_id). Used to prevent double-deduction when AMS remain increases (spool swap) or events replay.
    segment_idx: Mapped[int | None] = mapped_column(Integer, nullable=True)

    grams: Mapped[int] = mapped_column(Integer, nullable=False)
    # Requested vs effective grams (effective is clamped by stock remaining_grams)
    grams_requested: Mapped[int | None] = mapped_column(Integer, nullable=True)
    grams_effective: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


Index("ix_consumption_records_job_id", ConsumptionRecord.job_id)
Index("ix_consumption_records_spool_id", ConsumptionRecord.spool_id)
Index("ix_consumption_records_stock_id", ConsumptionRecord.stock_id)
Index("ix_consumption_records_job_tray", ConsumptionRecord.job_id, ConsumptionRecord.tray_id)
Index(
    "ux_consumption_records_job_tray_segment",
    ConsumptionRecord.job_id,
    ConsumptionRecord.tray_id,
    ConsumptionRecord.segment_idx,
    unique=True,
    postgresql_where=text("tray_id is not null and segment_idx is not null"),
)


