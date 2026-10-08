"""stored files

Offender photos and evidence files uploaded into the system. Files live in a
content-addressed store (see app/utils/file_store.py); these columns record
the SHA-256 that names them plus what is needed to serve them back.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-08 16:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('criminals', sa.Column('photo_sha256', sa.String(length=64), nullable=True))
    op.add_column('criminals', sa.Column('photo_content_type', sa.String(length=50), nullable=True))
    op.add_column('evidence', sa.Column('file_content_type', sa.String(length=50), nullable=True))
    op.add_column('evidence', sa.Column('file_name', sa.String(length=255), nullable=True))
    op.add_column('evidence', sa.Column('file_size', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('evidence', schema=None) as batch_op:
        batch_op.drop_column('file_size')
        batch_op.drop_column('file_name')
        batch_op.drop_column('file_content_type')
    with op.batch_alter_table('criminals', schema=None) as batch_op:
        batch_op.drop_column('photo_content_type')
        batch_op.drop_column('photo_sha256')
