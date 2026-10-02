"""security governance and integrity

Adds account-security state (lockout, forced password change, token
versioning), revoked-token storage, append-only AI review history, per-user
notification read receipts, tamper-evident audit fields and evidence hashes.

Data fixes:
* AI prediction confidences are normalised to the 0-1 fraction the API writes
  (the original seeder stored 0-100 percentages in the same columns).
* Existing reviewed predictions get a legacy row in ai_prediction_reviews.

Integrity:
* audit_logs and ai_prediction_reviews become append-only via database
  triggers. NOTE for future migrations: SQLite "batch" alterations recreate
  the table, which drops these triggers - re-create them afterwards.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-02 22:05:41.005420
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APPEND_ONLY_TABLES = ("audit_logs", "ai_prediction_reviews")


def upgrade() -> None:
    op.create_table('revoked_tokens',
    sa.Column('jti', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('jti')
    )
    with op.batch_alter_table('revoked_tokens', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_revoked_tokens_expires_at'), ['expires_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_revoked_tokens_user_id'), ['user_id'], unique=False)

    op.create_table('ai_prediction_reviews',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('prediction_id', sa.Integer(), nullable=False),
    sa.Column('reviewer_id', sa.Integer(), nullable=True),
    sa.Column('reviewer_username', sa.String(length=50), nullable=True),
    sa.Column('previous_status', sa.String(length=20), nullable=True),
    sa.Column('decision', sa.String(length=20), nullable=False),
    sa.Column('remarks', sa.Text(), nullable=False),
    sa.Column('override_crime_type', sa.String(length=100), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['prediction_id'], ['ai_predictions.id'], ),
    sa.ForeignKeyConstraint(['reviewer_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('ai_prediction_reviews', schema=None) as batch_op:
        batch_op.create_index('ix_ai_prediction_reviews_prediction', ['prediction_id', 'id'], unique=False)

    op.create_table('notification_reads',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('notification_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['notification_id'], ['notifications.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('notification_id', 'user_id', name='uq_notification_read')
    )
    with op.batch_alter_table('notification_reads', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_notification_reads_notification_id'), ['notification_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_notification_reads_user_id'), ['user_id'], unique=False)

    op.execute("UPDATE audit_logs SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('request_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('entry_hash', sa.String(length=64), nullable=True))
        batch_op.alter_column('created_at',
               existing_type=sa.DateTime(timezone=True),
               nullable=False,
               existing_server_default=sa.text('(CURRENT_TIMESTAMP)'))
        batch_op.create_index(batch_op.f('ix_audit_logs_request_id'), ['request_id'], unique=False)

    with op.batch_alter_table('evidence', schema=None) as batch_op:
        batch_op.add_column(sa.Column('file_sha256', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('created_by_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_evidence_created_by_id_users', 'users', ['created_by_id'], ['id'])

    with op.batch_alter_table('ml_models', schema=None) as batch_op:
        batch_op.add_column(sa.Column('activated_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('activated_by_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_ml_models_activated_by_id_users', 'users', ['activated_by_id'], ['id'])

    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dedup_key', sa.String(length=120), nullable=True))
        batch_op.create_index(batch_op.f('ix_notifications_dedup_key'), ['dedup_key'], unique=False)

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('must_change_password', sa.Boolean(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('failed_login_attempts', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('token_version', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=True))

    # Normalise legacy 0-100 confidence values to the 0-1 fraction used by the API.
    for column in ("crime_type_confidence", "gang_affiliation_probability", "confidence_overall"):
        op.execute(f"UPDATE ai_predictions SET {column} = {column} / 100.0 WHERE {column} > 1.0")

    # Preserve existing review decisions as the first history entry.
    op.execute(
        """
        INSERT INTO ai_prediction_reviews
            (prediction_id, reviewer_id, reviewer_username, previous_status, decision,
             remarks, override_crime_type, created_at)
        SELECT p.id, p.reviewed_by_id, u.username, 'pending', p.review_status,
               COALESCE(p.officer_remarks, '(legacy review - no reason recorded)'),
               p.override_crime_type, COALESCE(p.reviewed_at, p.created_at, CURRENT_TIMESTAMP)
        FROM ai_predictions p LEFT JOIN users u ON u.id = p.reviewed_by_id
        WHERE p.review_status IS NOT NULL AND p.review_status != 'pending'
        """
    )

    _create_append_only_triggers()


def downgrade() -> None:
    _drop_append_only_triggers()

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('password_changed_at')
        batch_op.drop_column('last_login_at')
        batch_op.drop_column('token_version')
        batch_op.drop_column('locked_until')
        batch_op.drop_column('failed_login_attempts')
        batch_op.drop_column('must_change_password')

    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_notifications_dedup_key'))
        batch_op.drop_column('dedup_key')

    with op.batch_alter_table('ml_models', schema=None) as batch_op:
        batch_op.drop_constraint('fk_ml_models_activated_by_id_users', type_='foreignkey')
        batch_op.drop_column('activated_by_id')
        batch_op.drop_column('activated_at')

    with op.batch_alter_table('evidence', schema=None) as batch_op:
        batch_op.drop_constraint('fk_evidence_created_by_id_users', type_='foreignkey')
        batch_op.drop_column('created_by_id')
        batch_op.drop_column('file_sha256')

    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_audit_logs_request_id'))
        batch_op.alter_column('created_at',
               existing_type=sa.DateTime(timezone=True),
               nullable=True,
               existing_server_default=sa.text('(CURRENT_TIMESTAMP)'))
        batch_op.drop_column('entry_hash')
        batch_op.drop_column('request_id')

    with op.batch_alter_table('notification_reads', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_notification_reads_user_id'))
        batch_op.drop_index(batch_op.f('ix_notification_reads_notification_id'))

    op.drop_table('notification_reads')
    with op.batch_alter_table('ai_prediction_reviews', schema=None) as batch_op:
        batch_op.drop_index('ix_ai_prediction_reviews_prediction')

    op.drop_table('ai_prediction_reviews')
    with op.batch_alter_table('revoked_tokens', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_revoked_tokens_user_id'))
        batch_op.drop_index(batch_op.f('ix_revoked_tokens_expires_at'))

    op.drop_table('revoked_tokens')


def _create_append_only_triggers() -> None:
    dialect = op.get_bind().dialect.name
    for table in APPEND_ONLY_TABLES:
        if dialect == "sqlite":
            for action in ("UPDATE", "DELETE"):
                op.execute(
                    f"CREATE TRIGGER IF NOT EXISTS trg_{table}_no_{action.lower()} "
                    f"BEFORE {action} ON {table} "
                    f"BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END;"
                )
        elif dialect == "postgresql":
            op.execute(
                f"""
                CREATE OR REPLACE FUNCTION {table}_append_only() RETURNS trigger AS $$
                BEGIN RAISE EXCEPTION '{table} is append-only'; END;
                $$ LANGUAGE plpgsql;
                """
            )
            op.execute(
                f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} "
                f"FOR EACH ROW EXECUTE FUNCTION {table}_append_only();"
            )


def _drop_append_only_triggers() -> None:
    dialect = op.get_bind().dialect.name
    for table in APPEND_ONLY_TABLES:
        if dialect == "sqlite":
            for action in ("update", "delete"):
                op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_no_{action}")
        elif dialect == "postgresql":
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only ON {table}")
            op.execute(f"DROP FUNCTION IF EXISTS {table}_append_only()")
