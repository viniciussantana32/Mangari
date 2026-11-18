from functools import wraps
from pathlib import Path
import re

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.forms.chapter_forms import ChapterMetadataForm, ChapterUploadForm
from app.models.chapter import Chapter
from app.models.manga import Manga
from app.models.reading_progress import ReadingProgress
from app.services.anilist_service import get_manga_by_id
from app.services.chapter_import_service import ChapterImportError, import_chapter
from app.services.reader_service import (
    delete_chapter,
    get_chapter,
    get_chapter_dir,
    get_chapter_pages,
    get_progress,
    list_chapters,
    save_progress,
)
from app.services.storage_service import get_storage_root

reader_bp = Blueprint('reader', __name__, url_prefix='/reader')
_PAGE_NAME = re.compile(r'^\d{4,}\.(?:jpg|jpeg|png|webp|gif)$', re.IGNORECASE)
_MIME_TYPES = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.webp': 'image/webp',
    '.gif': 'image/gif',
}


def format_chapter_display(chapter_number, raw_title=None):
    """
    Formata o título do capítulo evitando duplicações como 'Capítulo 1: Capítulo 1'.
    Se o título cadastrado já começa com indicação do número do capítulo, normaliza ou usa 'Capítulo X — Título'.
    """
    num_str = f"{chapter_number.normalize():f}" if hasattr(chapter_number, 'normalize') else str(chapter_number)
    base_prefix = f"Capítulo {num_str}"
    if not raw_title:
        return base_prefix

    clean_title = raw_title.strip()
    if not clean_title:
        return base_prefix

    # Verificar se o título cadastrado é exatamente igual ou repete 'Capítulo X' / 'Cap. X'
    pattern = rf'^(?:cap[íi]tulo|cap\.?)\s*{re.escape(num_str)}[\s:\-—–]*(.*)$'
    match = re.match(pattern, clean_title, re.IGNORECASE)
    if match:
        rest = match.group(1).strip()
        if not rest:
            return base_prefix
        return f"{base_prefix} — {rest}"

    # Se o título for apenas o próprio número
    if clean_title == num_str:
        return base_prefix

    return f"{base_prefix} — {clean_title}"


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped_view(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped_view


@reader_bp.route('/manage')
@admin_required
def manage():
    manga_rows = (
        db.session.query(Chapter.anilist_id, func.count(Chapter.id))
        .group_by(Chapter.anilist_id)
        .order_by(Chapter.anilist_id)
        .all()
    )
    manga_items = []
    for anilist_id, chapter_count in manga_rows:
        manga, error = get_manga_by_id(anilist_id)
        title_data = (manga or {}).get('title') or {}
        cover_data = (manga or {}).get('coverImage') or {}
        manga_items.append({
            'anilist_id': anilist_id,
            'title': title_data.get('english') or title_data.get('romaji') or title_data.get('native'),
            'cover': cover_data.get('large') or cover_data.get('extraLarge'),
            'chapter_count': chapter_count,
            'unavailable': bool(error or not manga),
        })
    return render_template('reader/manage.html', manga_items=manga_items)


@reader_bp.route('/manage/manga/<int:anilist_id>')
@admin_required
def manage_manga_chapters(anilist_id):
    if not 1 <= anilist_id <= 999999999:
        abort(404)
    manga, error = get_manga_by_id(anilist_id)
    chapters = (
        Chapter.query.filter_by(anilist_id=anilist_id)
        .order_by(Chapter.chapter_number.asc())
        .all()
    )
    availability = {
        chapter.id: (
            chapter.is_available
            and len(get_chapter_pages(chapter)) == chapter.page_count
        )
        for chapter in chapters
    }
    return render_template(
        'reader/manage_manga.html',
        anilist_id=anilist_id,
        manga=manga or {},
        manga_error=bool(error or not manga),
        chapters=chapters,
        availability=availability,
    )


@reader_bp.route('/import', methods=['GET', 'POST'])
@admin_required
def import_view():
    """
    Rota legada de importação de capítulos:
    Redireciona com segurança para a rota oficial de gerenciamento e upload de capítulos (/admin/chapters).
    Mantida protegida por @admin_required (retornando 403 Forbidden para usuários sem privilégio administrativo).
    """
    manga_id = request.args.get('manga_id', type=int)
    if manga_id:
        return redirect(url_for('admin.chapters_list', manga_id=manga_id))
    return redirect(url_for('admin.chapters_list'))



@reader_bp.route('/chapter/<int:chapter_id>/delete', methods=['POST'])
@admin_required
def delete_view(chapter_id):
    chapter = db.get_or_404(Chapter, chapter_id)
    anilist_id = chapter.anilist_id
    try:
        delete_chapter(chapter)
    except (OSError, SQLAlchemyError, ValueError):
        current_app.logger.exception('Failed to remove a chapter and its stored pages')
        flash('Não foi possível concluir a exclusão do capítulo.', 'danger')
    else:
        flash('Capítulo excluído.', 'success')
    return redirect(url_for('reader.manage_manga_chapters', anilist_id=anilist_id))


@reader_bp.route('/chapter/<int:chapter_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_chapter(chapter_id):
    chapter = db.get_or_404(Chapter, chapter_id)
    form = ChapterMetadataForm(obj=chapter)
    if form.validate_on_submit():
        chapter.chapter_title = (form.chapter_title.data or '').strip() or None
        chapter.volume_number = form.volume_number.data
        chapter.is_available = form.is_available.data
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception('Failed to update chapter metadata')
            flash('Não foi possível salvar as alterações do capítulo.', 'danger')
        else:
            flash('Metadados do capítulo atualizados.', 'success')
            return redirect(url_for('reader.manage_manga_chapters', anilist_id=chapter.anilist_id))
    return render_template('reader/edit.html', chapter=chapter, form=form)


@reader_bp.route('/manga/<int:anilist_id>/chapters')
@login_required
def chapter_list(anilist_id):
    if not 1 <= anilist_id <= 999999999:
        abort(404)
    manga, error = get_manga_by_id(anilist_id)
    if error or not manga:
        flash('Não foi possível carregar os dados da obra na AniList.', 'warning')
        manga = {'title': {'romaji': f'Obra AniList {anilist_id}'}, 'coverImage': {}}
    chapters = list_chapters(anilist_id)
    progress_by_chapter = {
        item.chapter_id: item
        for item in ReadingProgress.query.filter_by(user_id=current_user.id)
        .join(Chapter)
        .filter(Chapter.anilist_id == anilist_id)
        .all()
    }
    return render_template(
        'reader/chapters.html',
        anilist_id=anilist_id,
        manga=manga,
        chapters=chapters,
        progress_by_chapter=progress_by_chapter,
    )


@reader_bp.route('/chapter/<int:chapter_id>')
@login_required
def read_chapter(chapter_id):
    chapter = get_chapter(chapter_id)
    if not chapter:
        abort(404)
    if chapter.file_type == 'pdf':
        return redirect(url_for('reader.read_pdf_chapter', chapter_id=chapter.id))
    pages = get_chapter_pages(chapter)
    if len(pages) != chapter.page_count:
        flash('Os arquivos deste capítulo estão incompletos ou indisponíveis.', 'danger')
        return redirect(url_for('reader.chapter_list', anilist_id=chapter.anilist_id))

    chapters = list_chapters(chapter.anilist_id)
    chapter_index = next(index for index, item in enumerate(chapters) if item.id == chapter.id)
    previous_chapter = chapters[chapter_index - 1] if chapter_index > 0 else None
    next_chapter = chapters[chapter_index + 1] if chapter_index + 1 < len(chapters) else None
    manga, _ = get_manga_by_id(chapter.anilist_id)
    title_data = (manga or {}).get('title') or {}
    manga_title = title_data.get('english') or title_data.get('romaji') or title_data.get('native') or 'Mangá'
    chapter_display_title = format_chapter_display(chapter.chapter_number, chapter.chapter_title)
    progress = get_progress(current_user.id, chapter.id)
    return render_template(
        'reader/chapter.html',
        chapter=chapter,
        manga_title=manga_title,
        chapter_display_title=chapter_display_title,
        pages=pages,
        chapters=chapters,
        previous_chapter=previous_chapter,
        next_chapter=next_chapter,
        progress=progress,
    )


@reader_bp.route('/chapter/<int:chapter_id>/pdf')
@login_required
def read_pdf_chapter(chapter_id):
    chapter = get_chapter(chapter_id)
    if not chapter or chapter.file_type != 'pdf':
        abort(404)
    storage_root = get_storage_root()
    raw_path = str(getattr(chapter, 'folder_path', '') or '').replace('\\', '/').strip('/')
    for prefix in ('storage/manga/', 'manga/'):
        if raw_path.startswith(prefix):
            raw_path = raw_path[len(prefix):]
            break
    full_path = (storage_root / raw_path).resolve()
    if not full_path.is_relative_to(storage_root) or not full_path.is_file():
        flash('Os arquivos deste capítulo estão incompletos ou indisponíveis.', 'danger')
        return redirect(url_for('reader.chapter_list', anilist_id=chapter.anilist_id))

    chapters = list_chapters(chapter.anilist_id)
    chapter_index = next((index for index, item in enumerate(chapters) if item.id == chapter.id), 0)
    previous_chapter = chapters[chapter_index - 1] if chapter_index > 0 else None
    next_chapter = chapters[chapter_index + 1] if chapter_index + 1 < len(chapters) else None
    manga, _ = get_manga_by_id(chapter.anilist_id)
    title_data = (manga or {}).get('title') or {}
    manga_title = title_data.get('english') or title_data.get('romaji') or title_data.get('native') or 'Mangá'
    chapter_display_title = format_chapter_display(chapter.chapter_number, chapter.chapter_title)
    pdf_url = url_for('reader.serve_pdf_file', chapter_id=chapter.id)
    progress = get_progress(current_user.id, chapter.id)

    return render_template(
        'reader/pdf_reader.html',
        chapter=chapter,
        manga_title=manga_title,
        chapter_display_title=chapter_display_title,
        chapters=chapters,
        previous_chapter=previous_chapter,
        next_chapter=next_chapter,
        pdf_url=pdf_url,
        progress=progress,
    )


@reader_bp.route('/chapter/<int:chapter_id>/view.pdf')
@login_required
def serve_pdf_file(chapter_id):
    chapter = get_chapter(chapter_id)
    if not chapter or chapter.file_type != 'pdf':
        abort(404)
    storage_root = get_storage_root()
    raw_path = str(getattr(chapter, 'folder_path', '') or '').replace('\\', '/').strip('/')
    for prefix in ('storage/manga/', 'manga/'):
        if raw_path.startswith(prefix):
            raw_path = raw_path[len(prefix):]
            break
    full_path = (storage_root / raw_path).resolve()
    if not full_path.is_relative_to(storage_root) or not full_path.is_file():
        abort(404)
    response = send_file(
        full_path,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=chapter.original_filename or f'capitulo_{chapter.chapter_number}.pdf',
    )
    response.headers['Cache-Control'] = 'private, max-age=0, must-revalidate'
    return response


@reader_bp.route('/chapter/<int:chapter_id>/page/<int:page_number>')
@login_required
def serve_page(chapter_id, page_number):
    chapter = get_chapter(chapter_id)
    if not chapter or not 1 <= page_number <= chapter.page_count:
        abort(404)
    return _send_chapter_page(chapter, page_number)


@reader_bp.route('/media/<int:anilist_id>/<int:chapter_id>/<int:page_number>')
@login_required
def serve_media(anilist_id, chapter_id, page_number):
    chapter = get_chapter(chapter_id)
    if not chapter or chapter.anilist_id != anilist_id or not 1 <= page_number <= chapter.page_count:
        abort(404)
    return _send_chapter_page(chapter, page_number)


def _send_chapter_page(chapter, page_number):
    pages = get_chapter_pages(chapter)
    if len(pages) != chapter.page_count or page_number > len(pages):
        abort(404)
    page_path = pages[page_number - 1].resolve()
    storage_root = get_storage_root()
    if not page_path.is_relative_to(storage_root) or not _PAGE_NAME.fullmatch(page_path.name):
        abort(404)
    if not page_path.is_file():
        abort(404)
    suffix = page_path.suffix.lower()
    mimetype = _MIME_TYPES.get(suffix, 'application/octet-stream')
    response = send_file(page_path, mimetype=mimetype, conditional=True, max_age=0)
    response.headers['Cache-Control'] = 'private, max-age=0, must-revalidate'
    return response


@reader_bp.route('/chapter/<int:chapter_id>/progress', methods=['POST'])
@login_required
def update_progress(chapter_id):
    chapter = get_chapter(chapter_id)
    if not chapter:
        return jsonify({'saved': False, 'message': 'O capítulo não está disponível.'}), 404
    payload = request.get_json(silent=True) or {}
    try:
        raw_page = payload.get('current_page')
        if isinstance(raw_page, bool):
            raise ValueError
        if isinstance(raw_page, int):
            current_page = raw_page
        elif isinstance(raw_page, float):
            if not raw_page.is_integer():
                raise ValueError
            current_page = int(raw_page)
        elif isinstance(raw_page, str):
            candidate = raw_page.strip()
            if not re.fullmatch(r'\d+', candidate):
                raise ValueError
            current_page = int(candidate)
        else:
            raise ValueError
        completed_value = payload.get('is_completed', False)
        if not isinstance(completed_value, bool):
            raise ValueError
        completed = completed_value
    except (TypeError, ValueError):
        return jsonify({'saved': False, 'message': 'A página informada é inválida.'}), 400
    try:
        progress = save_progress(current_user.id, chapter, current_page, completed)
    except ValueError as error:
        return jsonify({'saved': False, 'message': str(error)}), 400
    except SQLAlchemyError:
        current_app.logger.exception('Failed to save reading progress')
        return jsonify({'saved': False, 'message': 'Não foi possível salvar seu progresso.'}), 500
    return jsonify({
        'saved': True,
        'current_page': progress.current_page,
        'is_completed': progress.is_completed,
    })


@reader_bp.route('/manga/<int:anilist_id>')
@login_required
def reader_index(anilist_id):
    return redirect(url_for('reader.chapter_list', anilist_id=anilist_id))
