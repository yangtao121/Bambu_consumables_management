"""init

Revision ID: 0001_init
Revises:
Create Date: 2025-12-15

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "printers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ip", sa.Text(), nullable=False),
        sa.Column("serial", sa.Text(), nullable=False),
        sa.Column("alias", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("lan_access_code_enc", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_printers_serial", "printers", ["serial"], unique=True)

    op.create_table(
        "raw_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("printer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("printers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_raw_events_printer_id_received_at", "raw_events", ["printer_id", "received_at"])
    op.create_index("ix_raw_events_payload_hash", "raw_events", ["payload_hash"])

    op.create_table(
        "normalized_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("printer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("printers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("raw_event_id", sa.BigInteger(), sa.ForeignKey("raw_events.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ux_normalized_events_event_id", "normalized_events", ["event_id"], unique=True)
    op.create_index("ix_normalized_events_printer_id_occurred_at", "normalized_events", ["printer_id", "occurred_at"])
    op.create_index("ix_normalized_events_type", "normalized_events", ["type"])

    op.create_table(
        "spools",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("material", sa.Text(), nullable=False),
        sa.Column("color", sa.Text(), nullable=False),
        sa.Column("brand", sa.Text(), nullable=True),
        sa.Column("diameter_mm", sa.Numeric(4, 2), nullable=False, server_default=sa.text("1.75")),
        sa.Column("initial_grams", sa.Integer(), nullable=False),
        sa.Column("tare_grams", sa.Integer(), nullable=True),
        sa.Column("price_total", sa.Numeric(10, 2), nullable=True),
        sa.Column("price_per_kg", sa.Numeric(10, 2), nullable=True),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("remaining_grams_est", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_spools_status", "spools", ["status"])

    op.create_table(
        "tray_mappings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("printer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("printers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tray_id", sa.Integer(), nullable=False),
        sa.Column("spool_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("spools.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("bound_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("unbound_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_tray_mappings_printer_id_tray_id", "tray_mappings", ["printer_id", "tray_id"])
    op.create_index("ix_tray_mappings_spool_id", "tray_mappings", ["spool_id"])
    op.create_index(
        "ux_tray_mappings_active_printer_tray",
        "tray_mappings",
        ["printer_id", "tray_id"],
        unique=True,
        postgresql_where=sa.text("unbound_at IS NULL"),
    )

    op.create_table(
        "print_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("printer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("printers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_key", sa.Text(), nullable=True),
        sa.Column("file_name", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("spool_binding_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_print_jobs_printer_id_started_at", "print_jobs", ["printer_id", "started_at"])
    op.create_index(
        "ux_print_jobs_printer_job_key",
        "print_jobs",
        ["printer_id", "job_key"],
        unique=True,
        postgresql_where=sa.text("job_key IS NOT NULL"),
    )

    op.create_table(
        "consumption_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("print_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("spool_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("spools.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("grams", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_consumption_records_job_id", "consumption_records", ["job_id"])
    op.create_index("ix_consumption_records_spool_id", "consumption_records", ["spool_id"])

    op.create_table(
        "inventory_adjustments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("spool_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("spools.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("delta_grams", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_inventory_adjustments_spool_id", "inventory_adjustments", ["spool_id"])


def downgrade() -> None:
    op.drop_index("ix_inventory_adjustments_spool_id", table_name="inventory_adjustments")
    op.drop_table("inventory_adjustments")

    op.drop_index("ix_consumption_records_spool_id", table_name="consumption_records")
    op.drop_index("ix_consumption_records_job_id", table_name="consumption_records")
    op.drop_table("consumption_records")

    op.drop_index("ux_print_jobs_printer_job_key", table_name="print_jobs")
    op.drop_index("ix_print_jobs_printer_id_started_at", table_name="print_jobs")
    op.drop_table("print_jobs")

    op.drop_index("ux_tray_mappings_active_printer_tray", table_name="tray_mappings")
    op.drop_index("ix_tray_mappings_spool_id", table_name="tray_mappings")
    op.drop_index("ix_tray_mappings_printer_id_tray_id", table_name="tray_mappings")
    op.drop_table("tray_mappings")

    op.drop_index("ix_spools_status", table_name="spools")
    op.drop_table("spools")

    op.drop_index("ix_normalized_events_type", table_name="normalized_events")
    op.drop_index("ix_normalized_events_printer_id_occurred_at", table_name="normalized_events")
    op.drop_index("ux_normalized_events_event_id", table_name="normalized_events")
    op.drop_table("normalized_events")

    op.drop_index("ix_raw_events_payload_hash", table_name="raw_events")
    op.drop_index("ix_raw_events_printer_id_received_at", table_name="raw_events")
    op.drop_table("raw_events")

    op.drop_index("ix_printers_serial", table_name="printers")
    op.drop_table("printers")


