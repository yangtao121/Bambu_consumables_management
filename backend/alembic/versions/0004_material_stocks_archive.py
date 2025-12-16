"""material stocks archive (soft delete)

Revision ID: 0004_material_stocks_archive
Revises: 0003_ams_color_mappings
Create Date: 2025-12-16

"""

# pyright: reportMissingImports=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import alembic.op as op
import sqlalchemy as sa

revision = "0004_material_stocks_archive"
down_revision = "0003_ams_color_mappings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "material_stocks",
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "material_stocks",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Replace full unique index with partial unique index (active only)
    op.drop_index("ux_material_stocks_key", table_name="material_stocks")
    op.create_index(
        "ux_material_stocks_key_active",
        "material_stocks",
        ["material", "color", "brand"],
        unique=True,
        postgresql_where=sa.text("is_archived = false"),
    )


def downgrade() -> None:
    op.drop_index("ux_material_stocks_key_active", table_name="material_stocks")

    # Best-effort: remove archived rows to satisfy full unique index.
    op.execute("DELETE FROM material_stocks WHERE is_archived = true;")

    op.create_index("ux_material_stocks_key", "material_stocks", ["material", "color", "brand"], unique=True)
    op.drop_column("material_stocks", "archived_at")
    op.drop_column("material_stocks", "is_archived")
