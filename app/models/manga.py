from datetime import datetime, timezone

from app.extensions import db


class Manga(db.Model):
    __tablename__ = 'mangas'

    id = db.Column(db.Integer, primary_key=True)
    anilist_id = db.Column(db.Integer, unique=True, nullable=True, index=True)
    title = db.Column(db.String(255), nullable=False, index=True)
    alternative_titles = db.Column(db.String(500), nullable=True)
    synopsis = db.Column(db.Text, nullable=True)
    cover_image = db.Column(db.String(500), nullable=True)
    banner_image = db.Column(db.String(500), nullable=True)
    banner_position = db.Column(db.String(20), nullable=True, default='center')
    genres = db.Column(db.String(255), nullable=True)
    author = db.Column(db.String(255), nullable=True)
    publication_status = db.Column(db.String(50), nullable=True, default='RELEASING')
    anilist_chapters = db.Column(db.Integer, nullable=True)
    start_date = db.Column(db.String(50), nullable=True)
    end_date = db.Column(db.String(50), nullable=True)
    is_visible = db.Column(db.Boolean, nullable=False, default=True)
    is_featured = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    chapters = db.relationship('Chapter', back_populates='manga', cascade='all, delete-orphan')
    comments = db.relationship('Comment', back_populates='manga', cascade='all, delete-orphan')

    @property
    def banner_url(self):
        return self.banner_image or self.cover_image or ''

    @property
    def is_cover_banner(self):
        """Retorna True se a imagem de banner configurada for uma capa vertical ou ausente."""
        if not self.banner_image:
            return True
        if self.cover_image and self.banner_image == self.cover_image:
            return True
        if '/cover/' in self.banner_image:
            return True
        return False

    @property
    def total_chapters(self):
        """Retorna o total de capítulos conhecidos da obra (salvo via AniList/MangaDex/admin)."""
        if self.anilist_chapters and self.anilist_chapters > 0:
            return self.anilist_chapters
        return None

    def __repr__(self):
        return f'<Manga {self.title}>'
