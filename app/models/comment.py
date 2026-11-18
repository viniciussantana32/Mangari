from datetime import datetime, timezone

from app.extensions import db


class Comment(db.Model):
    __tablename__ = 'comments'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    manga_id = db.Column(db.Integer, db.ForeignKey('mangas.id', ondelete='SET NULL'), nullable=True)
    anilist_id = db.Column(db.Integer, nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='published')
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = db.relationship('User', back_populates='comments')
    manga = db.relationship('Manga', back_populates='comments')
    reports = db.relationship('CommentReport', back_populates='comment', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Comment {self.id} by User {self.user_id}>'
