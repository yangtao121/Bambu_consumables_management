"""material stocks (stock-mode)

Revision ID: 0002_material_stocks
Revises: 0001_init
Create Date: 2025-12-16

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_material_stocks"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "material_stocks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("material", sa.Text(), nullable=False),
        sa.Column("color", sa.Text(), nullable=False),
        sa.Column("brand", sa.Text(), nullable=False),
        sa.Column("roll_weight_grams", sa.Integer(), nullable=False, server_default=sa.text("1000")),
        sa.Column("remaining_grams", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ux_material_stocks_key", "material_stocks", ["material", "color", "brand"], unique=True)

    op.create_table(
        "material_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "stock_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("material_stocks.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("print_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("delta_grams", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_material_ledger_stock_id", "material_ledger", ["stock_id"])
    op.create_index("ix_material_ledger_job_id", "material_ledger", ["job_id"])

    # Extend consumption_records to support stock-mode
    op.add_column("consumption_records", sa.Column("stock_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("consumption_records", sa.Column("tray_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_consumption_records_stock_id",
        "consumption_records",
        "material_stocks",
        ["stock_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.alter_column("consumption_records", "spool_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.create_index("ix_consumption_records_stock_id", "consumption_records", ["stock_id"])
    op.create_index("ix_consumption_records_job_tray", "consumption_records", ["job_id", "tray_id"])


def downgrade() -> None:
    op.drop_index("ix_consumption_records_job_tray", table_name="consumption_records")
    op.drop_index("ix_consumption_records_stock_id", table_name="consumption_records")
    op.alter_column("consumption_records", "spool_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    op.drop_constraint("fk_consumption_records_stock_id", "consumption_records", type_="foreignkey")
    op.drop_column("consumption_records", "tray_id")
    op.drop_column("consumption_records", "stock_id")

    op.drop_index("ix_material_ledger_job_id", table_name="material_ledger")
    op.drop_index("ix_material_ledger_stock_id", table_name="material_ledger")
    op.drop_table("material_ledger")

    op.drop_index("ux_material_stocks_key", table_name="material_stocks")
    op.drop_table("material_stocks")

