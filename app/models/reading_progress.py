from datetime import datetime, timezone

from app.extensions import db


class ReadingProgress(db.Model):
    __tablename__ = 'reading_progress'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    chapter_id = db.Column(db.Integer, db.ForeignKey('chapters.id', ondelete='CASCADE'), nullable=False)
    current_page = db.Column(db.Integer, nullable=False, default=1)
    is_completed = db.Column(db.Boolean, nullable=False, default=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', back_populates='reading_progress')
    chapter = db.relationship('Chapter', back_populates='reading_progress')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'chapter_id', name='uq_user_chapter_progress'),
        db.CheckConstraint('current_page >= 1', name='ck_progress_page_positive'),
    )
