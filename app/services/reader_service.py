from pathlib import Path
import shutil
import uuid

from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.chapter import Chapter
from app.models.library_entry import LibraryEntry
from app.models.reading_progress import ReadingProgress
from app.services.storage_service import get_storage_root


def list_chapters(anilist_id):
    return (
        Chapter.query.filter_by(anilist_id=anilist_id, is_available=True)
        .order_by(Chapter.chapter_number.asc())
        .all()
    )


def get_chapter(chapter_id):
    return Chapter.query.filter_by(id=chapter_id, is_available=True).first()


def get_chapter_dir(chapter):
    """
    Resolve o diretório do capítulo de forma segura a partir de storage_root,
    tolerando caminhos gravados com ou sem o prefixo 'storage/manga/'.
    """
    storage_root = get_storage_root()
    raw_path = str(getattr(chapter, 'folder_path', '') or '').replace('\\', '/').strip('/')
    for prefix in ('storage/manga/', 'manga/'):
        if raw_path.startswith(prefix):
            raw_path = raw_path[len(prefix):]
            break
    resolved = (storage_root / raw_path).resolve()
    if not resolved.is_relative_to(storage_root):
        return None
    return resolved


_VALID_IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.gif')


def get_chapter_pages(chapter):
    chapter_dir = get_chapter_dir(chapter)
    if not chapter_dir or not chapter_dir.is_dir():
        return []
    pages = []
    for page_number in range(1, chapter.page_count + 1):
        found = None
        for ext in _VALID_IMAGE_EXTENSIONS:
            candidate = chapter_dir / f'{page_number:04d}{ext}'
            if candidate.is_file():
                found = candidate
                break
            # Suporte também a extensões em maiúsculas (ex: .JPG, .PNG, .WEBP)
            candidate_upper = chapter_dir / f'{page_number:04d}{ext.upper()}'
            if candidate_upper.is_file():
                found = candidate_upper
                break
        if found:
            pages.append(found)
    return pages


def get_progress(user_id, chapter_id):
    return ReadingProgress.query.filter_by(user_id=user_id, chapter_id=chapter_id).first()


def save_progress(user_id, chapter, current_page, is_completed=False):
    if current_page < 1 or current_page > chapter.page_count:
        raise ValueError('Página fora dos limites do capítulo.')

    try:
        progress = get_progress(user_id, chapter.id)
        if progress is None:
            progress = ReadingProgress(
                user_id=user_id,
                chapter_id=chapter.id,
                current_page=current_page,
            )
            db.session.add(progress)

        progress.current_page = current_page
        if is_completed:
            progress.is_completed = True
        library_entry = LibraryEntry.query.filter_by(
            user_id=user_id,
            anilist_id=chapter.anilist_id,
        ).first()
        if library_entry:
            chapter_number = chapter.chapter_number
            if chapter_number == chapter_number.to_integral_value():
                library_entry.current_chapter = max(
                    library_entry.current_chapter,
                    int(chapter_number),
                )
            if library_entry.reading_status == 'Want to Read':
                library_entry.reading_status = 'Reading'
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise
    return progress


def delete_chapter(chapter):
    storage_root = get_storage_root()
    chapter_dir = get_chapter_dir(chapter)
    if not chapter_dir or not chapter_dir.is_relative_to(storage_root):
        raise ValueError('O caminho do capítulo é inválido.')
    quarantine_dir = storage_root / f'.delete-{uuid.uuid4().hex}'
    moved = False
    if chapter_dir.exists():
        chapter_dir.replace(quarantine_dir)
        moved = True
    try:
        db.session.delete(chapter)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        if moved:
            quarantine_dir.replace(chapter_dir)
        raise
    if moved:
        shutil.rmtree(quarantine_dir)
