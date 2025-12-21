"""Fix consumption record timezone

Revision ID: 0008_fix_consumption_record_timezone
Revises: 0007_void_and_manual_consumption
Create Date: 2025-12-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '0008_fix_consumption_record_timezone'
down_revision: Union[str, None] = '0007_void_and_manual_consumption'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Update existing consumption_records created_at timestamps to be timezone-aware UTC
    # This converts existing naive UTC timestamps to explicit UTC timestamps
    op.execute("""
        UPDATE consumption_records 
        SET created_at = created_at AT TIME ZONE 'UTC'
        WHERE created_at IS NOT NULL
    """)


def downgrade() -> None:
    # Revert timezone-aware UTC timestamps back to naive UTC timestamps
    op.execute("""
        UPDATE consumption_records 
        SET created_at = created_at AT TIME ZONE 'UTC' AT TIME ZONE 'UTC'
        WHERE created_at IS NOT NULL
    """)
