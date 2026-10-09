"""case incident details

Adds the place of occurrence, the target and the modus operandi to cases.
They are stored as vocabulary keys (app.constants.CASE_DETAIL_FIELDS) and used
as observed inputs by the AI crime-type model. NULL means "not recorded".

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-09 08:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DETAIL_COLUMNS = ("location_type", "target_type", "modus_operandi")


def upgrade() -> None:
    for name in DETAIL_COLUMNS:
        op.add_column('cases', sa.Column(name, sa.String(length=32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('cases', schema=None) as batch_op:
        for name in reversed(DETAIL_COLUMNS):
            batch_op.drop_column(name)
