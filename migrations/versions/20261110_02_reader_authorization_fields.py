"""Add authorization and uploader fields to existing reader chapters.

Revision ID: 20261110_02
Revises: 20261110_01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '20261110_02'
down_revision = '20261110_01'
branch_labels = None
depends_on = None


def upgrade():
    inspector = inspect(op.get_bind())
    columns = {column['name'] for column in inspector.get_columns('chapters')}
    add_authorization = 'authorization_confirmed' not in columns
    add_uploader = 'uploaded_by_id' not in columns

    if add_authorization or add_uploader:
        with op.batch_alter_table('chapters') as batch_op:
            if add_authorization:
                batch_op.add_column(
                    sa.Column(
                        'authorization_confirmed',
                        sa.Boolean(),
                        nullable=False,
                        server_default=sa.false(),
                    )
                )
            if add_uploader:
                batch_op.add_column(sa.Column('uploaded_by_id', sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    'fk_chapters_uploaded_by_id_users',
                    'users',
                    ['uploaded_by_id'],
                    ['id'],
                    ondelete='SET NULL',
                )


def downgrade():
    inspector = inspect(op.get_bind())
    columns = {column['name'] for column in inspector.get_columns('chapters')}
    drop_authorization = 'authorization_confirmed' in columns
    drop_uploader = 'uploaded_by_id' in columns

    if drop_authorization or drop_uploader:
        with op.batch_alter_table('chapters') as batch_op:
            if drop_uploader:
                batch_op.drop_constraint('fk_chapters_uploaded_by_id_users', type_='foreignkey')
                batch_op.drop_column('uploaded_by_id')
            if drop_authorization:
                batch_op.drop_column('authorization_confirmed')
