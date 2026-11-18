from datetime import datetime, timezone

from app.extensions import db


class LibraryEntry(db.Model):
    __tablename__ = 'library_entries'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    anilist_id = db.Column(db.Integer, nullable=False)
    manga_title = db.Column(db.String(255), nullable=False)
    cover_image = db.Column(db.String(500), nullable=True)
    reading_status = db.Column(db.String(30), nullable=False, default='Want to Read')
    current_chapter = db.Column(db.Integer, default=0, nullable=False)
    personal_rating = db.Column(db.Float, default=0.0, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = db.relationship('User', back_populates='library_entries')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'anilist_id', name='uq_user_manga_library'),
    )

    def __repr__(self):
        return f'<LibraryEntry {self.manga_title}>'
