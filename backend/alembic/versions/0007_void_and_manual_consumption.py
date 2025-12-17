"""voidable consumptions + reversible ledger (manual friendly)

Revision ID: 0007_void_manual
Revises: 0006_ledger_price_tray
Create Date: 2025-12-17

"""

# pyright: reportMissingImports=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import alembic.op as op
import sqlalchemy as sa

revision = "0007_void_manual"
down_revision = "0006_ledger_price_tray"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Allow manual stock consumptions not tied to a job
    op.alter_column("consumption_records", "job_id", existing_type=sa.dialects.postgresql.UUID(), nullable=True)

    # Void / audit fields for consumptions
    op.add_column("consumption_records", sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("consumption_records", sa.Column("void_reason", sa.Text(), nullable=True))

    # Void / audit fields for material ledger rows
    op.add_column("material_ledger", sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("material_ledger", sa.Column("void_reason", sa.Text(), nullable=True))

    # Link reversal rows to original ledger row (optional)
    op.add_column("material_ledger", sa.Column("reversal_of_id", sa.dialects.postgresql.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_material_ledger_reversal_of",
        "material_ledger",
        "material_ledger",
        ["reversal_of_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_material_ledger_reversal_of_id", "material_ledger", ["reversal_of_id"])


def downgrade() -> None:
    op.drop_index("ix_material_ledger_reversal_of_id", table_name="material_ledger")
    op.drop_constraint("fk_material_ledger_reversal_of", "material_ledger", type_="foreignkey")
    op.drop_column("material_ledger", "reversal_of_id")
    op.drop_column("material_ledger", "void_reason")
    op.drop_column("material_ledger", "voided_at")

    op.drop_column("consumption_records", "void_reason")
    op.drop_column("consumption_records", "voided_at")

    # Revert to non-nullable job_id (NOTE: rows with NULL job_id would prevent downgrade)
    op.alter_column("consumption_records", "job_id", existing_type=sa.dialects.postgresql.UUID(), nullable=False)

