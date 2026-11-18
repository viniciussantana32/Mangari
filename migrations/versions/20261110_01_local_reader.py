"""Add local reader chapters and per-user reading progress.

Revision ID: 20261110_01
Revises:
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '20261110_01'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())

    if 'chapters' not in tables:
        op.create_table(
            'chapters',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('anilist_id', sa.Integer(), nullable=False),
            sa.Column('chapter_number', sa.Numeric(10, 3), nullable=False),
            sa.Column('chapter_title', sa.String(length=255), nullable=True),
            sa.Column('volume_number', sa.Numeric(10, 3), nullable=True),
            sa.Column('folder_path', sa.String(length=500), nullable=False, unique=True),
            sa.Column('page_count', sa.Integer(), nullable=False),
            sa.Column('is_available', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('authorization_confirmed', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('uploaded_by_id', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint('chapter_number >= 0', name='ck_chapter_number_nonnegative'),
            sa.CheckConstraint('page_count > 0', name='ck_chapter_page_count_positive'),
            sa.UniqueConstraint('anilist_id', 'chapter_number', name='uq_anilist_chapter_number'),
            sa.ForeignKeyConstraint(['uploaded_by_id'], ['users.id'], ondelete='SET NULL'),
        )
    if 'ix_chapters_anilist_id' not in {index['name'] for index in inspect(op.get_bind()).get_indexes('chapters')}:
        op.create_index('ix_chapters_anilist_id', 'chapters', ['anilist_id'])

    if 'reading_progress' not in set(inspect(op.get_bind()).get_table_names()):
        op.create_table(
            'reading_progress',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('chapter_id', sa.Integer(), nullable=False),
            sa.Column('current_page', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('is_completed', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint('current_page >= 1', name='ck_progress_page_positive'),
            sa.UniqueConstraint('user_id', 'chapter_id', name='uq_user_chapter_progress'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['chapter_id'], ['chapters.id'], ondelete='CASCADE'),
        )


def downgrade():
    tables = set(inspect(op.get_bind()).get_table_names())
    if 'reading_progress' in tables:
        op.drop_table('reading_progress')
    if 'chapters' in tables:
        indexes = {index['name'] for index in inspect(op.get_bind()).get_indexes('chapters')}
        if 'ix_chapters_anilist_id' in indexes:
            op.drop_index('ix_chapters_anilist_id', table_name='chapters')
        op.drop_table('chapters')
