from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MaterialLedger(Base):
    __tablename__ = "material_ledger"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # stock_id is nullable to support tray-only ledger rows (e.g. discarding trays)
    stock_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("material_stocks.id", ondelete="RESTRICT"), nullable=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("print_jobs.id", ondelete="SET NULL"), nullable=True
    )

    delta_grams: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Purchase/pricing fields (all optional for backward compatibility)
    rolls_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_per_roll: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    price_total: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    # Tray accounting (optional)
    has_tray: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tray_delta: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Optional kind for UI/filtering (purchase/adjustment/consumption/tray_discard)
    kind: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reversal_of_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("material_ledger.id", ondelete="SET NULL"), nullable=True
    )


Index("ix_material_ledger_stock_id", MaterialLedger.stock_id)
Index("ix_material_ledger_job_id", MaterialLedger.job_id)
Index("ix_material_ledger_created_at", MaterialLedger.created_at)
Index("ix_material_ledger_reversal_of_id", MaterialLedger.reversal_of_id)

