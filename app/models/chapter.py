from datetime import datetime, timezone

from app.extensions import db


class Chapter(db.Model):
    __tablename__ = 'chapters'

    id = db.Column(db.Integer, primary_key=True)
    anilist_id = db.Column(db.Integer, nullable=False, index=True)
    manga_id = db.Column(db.Integer, db.ForeignKey('mangas.id', ondelete='SET NULL'), nullable=True)
    chapter_number = db.Column(db.Numeric(10, 3), nullable=False)
    chapter_title = db.Column(db.String(255), nullable=True)
    volume_number = db.Column(db.Numeric(10, 3), nullable=True)
    folder_path = db.Column(db.String(500), nullable=False, unique=True)
    original_filename = db.Column(db.String(255), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)
    file_type = db.Column(db.String(20), nullable=True, default='archive')
    page_count = db.Column(db.Integer, nullable=False)
    is_available = db.Column(db.Boolean, nullable=False, default=True)
    status = db.Column(db.String(20), nullable=False, default='published')
    published_at = db.Column(db.DateTime, nullable=True)
    authorization_confirmed = db.Column(db.Boolean, nullable=False, default=False)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    manga = db.relationship('Manga', back_populates='chapters')
    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_id])
    reading_progress = db.relationship(
        'ReadingProgress',
        back_populates='chapter',
        cascade='all, delete-orphan',
    )

    __table_args__ = (
        db.UniqueConstraint('anilist_id', 'chapter_number', name='uq_anilist_chapter_number'),
        db.CheckConstraint('chapter_number >= 0', name='ck_chapter_number_nonnegative'),
        db.CheckConstraint('page_count > 0', name='ck_chapter_page_count_positive'),
    )

    def __repr__(self):
        return f'<Chapter {self.anilist_id} #{self.chapter_number}>'
