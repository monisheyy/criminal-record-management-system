"""case incident features

Adds officer-recorded incident facts to cases so the AI crime-type model can
use observed inputs instead of defaults. All columns are nullable: NULL means
"not recorded" and is reported to reviewers as a defaulted model input.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-03 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INCIDENT_COLUMNS = ("weapons_involved", "drug_involvement", "financial_motivation", "tech_involvement")


def upgrade() -> None:
    for name in INCIDENT_COLUMNS:
        op.add_column('cases', sa.Column(name, sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('cases', schema=None) as batch_op:
        for name in reversed(INCIDENT_COLUMNS):
            batch_op.drop_column(name)
