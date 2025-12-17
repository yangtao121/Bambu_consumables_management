"""consumption record segments (segment idempotency)

Revision ID: 0005_consumption_record_segments
Revises: 0004_material_stocks_archive
Create Date: 2025-12-16

"""

# pyright: reportMissingImports=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import alembic.op as op
import sqlalchemy as sa

revision = "0005_consumption_record_segments"
down_revision = "0004_material_stocks_archive"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("consumption_records", sa.Column("segment_idx", sa.Integer(), nullable=True))
    op.add_column("consumption_records", sa.Column("grams_requested", sa.Integer(), nullable=True))
    op.add_column("consumption_records", sa.Column("grams_effective", sa.Integer(), nullable=True))

    op.create_index(
        "ux_consumption_records_job_tray_segment",
        "consumption_records",
        ["job_id", "tray_id", "segment_idx"],
        unique=True,
        postgresql_where=sa.text("tray_id is not null and segment_idx is not null"),
    )


def downgrade() -> None:
    op.drop_index("ux_consumption_records_job_tray_segment", table_name="consumption_records")
    op.drop_column("consumption_records", "grams_effective")
    op.drop_column("consumption_records", "grams_requested")
    op.drop_column("consumption_records", "segment_idx")

