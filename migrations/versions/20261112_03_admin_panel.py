"""Add admin panel tables and fields: mangas, comments, comment_reports, admin_logs, user status and chapter metadata.

Revision ID: 20261112_03
Revises: 20261110_02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '20261112_03'
down_revision = '20261110_02'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    # 1. users: add is_active if not present
    user_columns = {col['name'] for col in inspector.get_columns('users')}
    if 'is_active' not in user_columns:
        with op.batch_alter_table('users') as batch_op:
            batch_op.add_column(
                sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true())
            )

    # 2. mangas table
    if 'mangas' not in tables:
        op.create_table(
            'mangas',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('anilist_id', sa.Integer(), nullable=True, unique=True),
            sa.Column('title', sa.String(length=255), nullable=False),
            sa.Column('alternative_titles', sa.String(length=500), nullable=True),
            sa.Column('synopsis', sa.Text(), nullable=True),
            sa.Column('cover_image', sa.String(length=500), nullable=True),
            sa.Column('banner_image', sa.String(length=500), nullable=True),
            sa.Column('genres', sa.String(length=255), nullable=True),
            sa.Column('author', sa.String(length=255), nullable=True),
            sa.Column('publication_status', sa.String(length=50), nullable=True, server_default='RELEASING'),
            sa.Column('anilist_chapters', sa.Integer(), nullable=True),
            sa.Column('start_date', sa.String(length=50), nullable=True),
            sa.Column('end_date', sa.String(length=50), nullable=True),
            sa.Column('is_visible', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('is_featured', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index('ix_mangas_anilist_id', 'mangas', ['anilist_id'])
        op.create_index('ix_mangas_title', 'mangas', ['title'])

    # 3. chapters: add manga_id and metadata columns if not present
    chapter_columns = {col['name'] for col in inspector.get_columns('chapters')}
    with op.batch_alter_table('chapters') as batch_op:
        if 'manga_id' not in chapter_columns:
            batch_op.add_column(sa.Column('manga_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                'fk_chapters_manga_id_mangas',
                'mangas',
                ['manga_id'],
                ['id'],
                ondelete='SET NULL',
            )
        if 'original_filename' not in chapter_columns:
            batch_op.add_column(sa.Column('original_filename', sa.String(length=255), nullable=True))
        if 'file_size' not in chapter_columns:
            batch_op.add_column(sa.Column('file_size', sa.Integer(), nullable=True))
        if 'file_type' not in chapter_columns:
            batch_op.add_column(sa.Column('file_type', sa.String(length=20), nullable=True, server_default='archive'))
        if 'status' not in chapter_columns:
            batch_op.add_column(sa.Column('status', sa.String(length=20), nullable=False, server_default='published'))
        if 'published_at' not in chapter_columns:
            batch_op.add_column(sa.Column('published_at', sa.DateTime(), nullable=True))

    # 4. comments table
    if 'comments' not in tables:
        op.create_table(
            'comments',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('manga_id', sa.Integer(), nullable=True),
            sa.Column('anilist_id', sa.Integer(), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('status', sa.String(length=20), nullable=False, server_default='published'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['manga_id'], ['mangas.id'], ondelete='SET NULL'),
        )
        op.create_index('ix_comments_anilist_id', 'comments', ['anilist_id'])

    # 5. comment_reports table
    if 'comment_reports' not in tables:
        op.create_table(
            'comment_reports',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('comment_id', sa.Integer(), nullable=False),
            sa.Column('reporter_id', sa.Integer(), nullable=False),
            sa.Column('reason', sa.String(length=255), nullable=False),
            sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['comment_id'], ['comments.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['reporter_id'], ['users.id'], ondelete='CASCADE'),
        )

    # 6. admin_logs table
    if 'admin_logs' not in tables:
        op.create_table(
            'admin_logs',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('admin_user_id', sa.Integer(), nullable=True),
            sa.Column('action', sa.String(length=100), nullable=False),
            sa.Column('entity_type', sa.String(length=50), nullable=False),
            sa.Column('entity_id', sa.Integer(), nullable=True),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['admin_user_id'], ['users.id'], ondelete='SET NULL'),
        )


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if 'admin_logs' in tables:
        op.drop_table('admin_logs')
    if 'comment_reports' in tables:
        op.drop_table('comment_reports')
    if 'comments' in tables:
        if 'ix_comments_anilist_id' in {idx['name'] for idx in inspector.get_indexes('comments')}:
            op.drop_index('ix_comments_anilist_id', table_name='comments')
        op.drop_table('comments')

    if 'chapters' in tables:
        chapter_columns = {col['name'] for col in inspector.get_columns('chapters')}
        with op.batch_alter_table('chapters') as batch_op:
            if 'manga_id' in chapter_columns:
                batch_op.drop_constraint('fk_chapters_manga_id_mangas', type_='foreignkey')
                batch_op.drop_column('manga_id')
            if 'original_filename' in chapter_columns:
                batch_op.drop_column('original_filename')
            if 'file_size' in chapter_columns:
                batch_op.drop_column('file_size')
            if 'file_type' in chapter_columns:
                batch_op.drop_column('file_type')
            if 'status' in chapter_columns:
                batch_op.drop_column('status')
            if 'published_at' in chapter_columns:
                batch_op.drop_column('published_at')

    if 'mangas' in tables:
        indexes = {idx['name'] for idx in inspector.get_indexes('mangas')}
        if 'ix_mangas_title' in indexes:
            op.drop_index('ix_mangas_title', table_name='mangas')
        if 'ix_mangas_anilist_id' in indexes:
            op.drop_index('ix_mangas_anilist_id', table_name='mangas')
        op.drop_table('mangas')

    if 'users' in tables:
        user_columns = {col['name'] for col in inspector.get_columns('users')}
        if 'is_active' in user_columns:
            with op.batch_alter_table('users') as batch_op:
                batch_op.drop_column('is_active')
