"""material ledger pricing and trays (backward compatible)

Revision ID: 0006_material_ledger_pricing_and_trays
Revises: 0005_consumption_record_segments
Create Date: 2025-12-17

"""

# pyright: reportMissingImports=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import alembic.op as op
import sqlalchemy as sa

revision = "0006_material_ledger_pricing_and_trays"
down_revision = "0005_consumption_record_segments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Allow tray-only ledger rows: stock_id can be NULL
    op.alter_column("material_ledger", "stock_id", existing_type=sa.dialects.postgresql.UUID(), nullable=True)

    # Purchase/pricing fields (all nullable for backward compatibility)
    op.add_column("material_ledger", sa.Column("rolls_count", sa.Integer(), nullable=True))
    op.add_column("material_ledger", sa.Column("price_per_roll", sa.Numeric(10, 2), nullable=True))
    op.add_column("material_ledger", sa.Column("price_total", sa.Numeric(10, 2), nullable=True))

    # Tray accounting fields
    op.add_column("material_ledger", sa.Column("has_tray", sa.Boolean(), nullable=True))
    op.add_column("material_ledger", sa.Column("tray_delta", sa.Integer(), nullable=True))

    # Optional kind for UI / filtering
    op.add_column("material_ledger", sa.Column("kind", sa.Text(), nullable=True))

    # Helpful index for tray-only queries & reporting scans
    op.create_index("ix_material_ledger_created_at", "material_ledger", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_material_ledger_created_at", table_name="material_ledger")

    op.drop_column("material_ledger", "kind")
    op.drop_column("material_ledger", "tray_delta")
    op.drop_column("material_ledger", "has_tray")
    op.drop_column("material_ledger", "price_total")
    op.drop_column("material_ledger", "price_per_roll")
    op.drop_column("material_ledger", "rolls_count")

    # Revert to non-nullable stock_id (NOTE: tray-only rows would prevent downgrade)
    op.alter_column("material_ledger", "stock_id", existing_type=sa.dialects.postgresql.UUID(), nullable=False)

