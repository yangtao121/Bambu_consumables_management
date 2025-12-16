"""AMS color mappings + rename brand 官方->拓竹

Revision ID: 0003_ams_color_mappings
Revises: 0002_material_stocks
Create Date: 2025-12-16

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_ams_color_mappings"
down_revision = "0002_material_stocks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ams_color_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("color_hex", sa.Text(), nullable=False),
        sa.Column("color_name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ux_ams_color_mappings_hex", "ams_color_mappings", ["color_hex"], unique=True)

    # Rename brand "官方" -> "拓竹".
    # If "拓竹" already exists for same (material,color), merge remaining_grams to avoid conflicts.
    # NOTE: asyncpg does not allow multiple SQL statements in one execute; keep each op.execute a single statement.
    op.execute(
        """
        WITH pairs AS (
            SELECT o.id AS old_id, t.id AS new_id
            FROM material_stocks o
            JOIN material_stocks t
              ON t.material = o.material
             AND t.color = o.color
             AND t.brand = '拓竹'
            WHERE o.brand = '官方'
        ),
        merged AS (
            UPDATE material_stocks tgt
               SET remaining_grams = tgt.remaining_grams + src.remaining_grams,
                   updated_at = now()
              FROM material_stocks src, pairs p
             WHERE p.new_id = tgt.id
               AND p.old_id = src.id
            RETURNING p.old_id
        )
        DELETE FROM material_stocks
         WHERE id IN (SELECT old_id FROM merged);
        """
    )
    op.execute("UPDATE material_stocks SET brand='拓竹', updated_at=now() WHERE brand='官方';")


def downgrade() -> None:
    # Downgrade only drops mapping table. Brand rename is not safely reversible.
    op.drop_index("ux_ams_color_mappings_hex", table_name="ams_color_mappings")
    op.drop_table("ams_color_mappings")

