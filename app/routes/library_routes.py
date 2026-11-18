import math

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.forms.library_forms import LibraryEntryForm
from app.models.library_entry import LibraryEntry
from app.models.chapter import Chapter
from app.models.reading_progress import ReadingProgress
from app.services.library_service import add_library_entry, get_user_library

library_bp = Blueprint('library', __name__, url_prefix='/library')


@library_bp.route('', methods=['GET'])
@login_required
def list_library():
    status = request.args.get('status', '')
    search = request.args.get('q', '').strip()
    entries = get_user_library(current_user, status=status or None, search=search or None)
    latest_progress = {}
    if entries:
        progress_rows = (
            db.session.query(Chapter.anilist_id, Chapter.chapter_number, Chapter.id, ReadingProgress.current_page, ReadingProgress.is_completed)
            .join(ReadingProgress, ReadingProgress.chapter_id == Chapter.id)
            .filter(ReadingProgress.user_id == current_user.id)
            .order_by(ReadingProgress.updated_at.desc())
            .all()
        )
        for row in progress_rows:
            latest_progress.setdefault(row.anilist_id, row)
    return render_template(
        'library/list.html',
        entries=entries,
        status=status,
        search=search,
        latest_progress=latest_progress,
    )


@library_bp.route('/add', methods=['POST'])
@login_required
def add_to_library():
    form = LibraryEntryForm()
    if form.validate_on_submit():
        entry, created = add_library_entry(
            current_user,
            int(form.anilist_id.data),
            form.manga_title.data.strip(),
            cover_image=form.cover_image.data,
            reading_status=form.reading_status.data,
            current_chapter=form.current_chapter.data or 0,
            personal_rating=form.personal_rating.data or 0.0,
        )
        if created:
            flash('Manga added to your library.', 'success')
        else:
            flash('This manga is already in your library.', 'info')
    else:
        flash('Please fill in the required fields.', 'danger')
    return redirect(request.referrer or url_for('main.index'))


@library_bp.route('/<int:entry_id>')
@login_required
def detail_library(entry_id):
    entry = LibraryEntry.query.filter_by(id=entry_id, user_id=current_user.id).first_or_404()
    return render_template('library/detail.html', entry=entry)


@library_bp.route('/<int:entry_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_library(entry_id):
    entry = LibraryEntry.query.filter_by(id=entry_id, user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        raw_current_chapter = request.form.get('current_chapter', entry.current_chapter)
        raw_rating = request.form.get('personal_rating', entry.personal_rating)
        try:
            if raw_current_chapter in (None, ''):
                entry.current_chapter = 0
            else:
                chapter_value = int(raw_current_chapter)
                if chapter_value < 0:
                    raise ValueError
                entry.current_chapter = chapter_value
            if raw_rating in (None, ''):
                entry.personal_rating = 0.0
            else:
                rating_value = float(raw_rating)
                if not math.isfinite(rating_value):
                    raise ValueError
                entry.personal_rating = rating_value
        except (TypeError, ValueError):
            flash('Os valores informados para capítulo e avaliação são inválidos.', 'danger')
            return redirect(url_for('library.detail_library', entry_id=entry.id))
        entry.reading_status = request.form.get('reading_status', entry.reading_status)
        db.session.commit()
        flash('Library entry updated.', 'success')
        return redirect(url_for('library.detail_library', entry_id=entry.id))
    return render_template('library/edit.html', entry=entry)


@library_bp.route('/<int:entry_id>/delete', methods=['POST'])
@login_required
def delete_library(entry_id):
    entry = LibraryEntry.query.filter_by(id=entry_id, user_id=current_user.id).first_or_404()
    db.session.delete(entry)
    db.session.commit()
    flash('Manga removed from your library.', 'success')
    return redirect(url_for('library.list_library'))
