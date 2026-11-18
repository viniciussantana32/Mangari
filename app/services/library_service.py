from app.extensions import db
from app.models.library_entry import LibraryEntry


def add_library_entry(user, anilist_id, manga_title, cover_image=None, reading_status='Want to Read', current_chapter=0, personal_rating=0.0):
    existing = LibraryEntry.query.filter_by(user_id=user.id, anilist_id=anilist_id).first()
    if existing:
        return existing, False

    entry = LibraryEntry(
        user_id=user.id,
        anilist_id=anilist_id,
        manga_title=manga_title,
        cover_image=cover_image,
        reading_status=reading_status,
        current_chapter=current_chapter,
        personal_rating=personal_rating,
    )
    db.session.add(entry)
    db.session.commit()
    return entry, True


def get_user_library(user, status=None, search=None):
    query = LibraryEntry.query.filter_by(user_id=user.id)
    if status:
        query = query.filter_by(reading_status=status)
    if search:
        query = query.filter(LibraryEntry.manga_title.ilike(f'%{search}%'))
    return query.order_by(LibraryEntry.created_at.desc()).all()


def get_library_item(entry_id, user):
    return LibraryEntry.query.filter_by(id=entry_id, user_id=user.id).first()
