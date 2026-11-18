from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import re

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user
from sqlalchemy import func, or_
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.forms.admin_forms import (
    ChapterPDFEditForm,
    ChapterPDFUploadForm,
    MangaForm,
    UserAdminEditForm,
)
from app.models.admin_log import AdminLog
from app.models.chapter import Chapter
from app.models.comment import Comment
from app.models.comment_report import CommentReport
from app.models.manga import Manga
from app.models.user import User
from app.services.anilist_service import get_manga_by_id, get_manga_search_results
from app.services.log_service import log_action
from app.services.manga_service import delete_manga_safely, list_admin_mangas
from app.services.report_service import (
    generate_mangas_csv,
    generate_mangas_pdf,
    generate_users_csv,
    generate_users_pdf,
    get_mangas_report_data,
    get_users_report_data,
)
from app.services.pdf_service import (
    PDFUploadError,
    delete_chapter_file,
    replace_chapter_pdf,
    save_chapter_pdf,
)
from app.services.translation_service import clean_html_tags, translate_text_to_portuguese
from app.services.storage_service import get_storage_root
from app.utils.decorators import admin_required

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.before_request
@admin_required
def before_admin_request():
    """Garante que todas as rotas do blueprint admin exijam autenticação de administrador."""
    pass


# -------------------------------------------------------------------------
# 1. Dashboard
# -------------------------------------------------------------------------
@admin_bp.route('')
@admin_bp.route('/dashboard')
def dashboard():
    total_mangas = Manga.query.count()
    total_chapters = Chapter.query.count()
    total_users = User.query.count()
    total_comments = Comment.query.count()
    pending_comments = Comment.query.filter_by(status='pending').count()
    pending_reports = CommentReport.query.filter_by(status='pending').count()

    recent_mangas = Manga.query.order_by(Manga.created_at.desc()).limit(5).all()
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    recent_logs = AdminLog.query.order_by(AdminLog.created_at.desc()).limit(8).all()

    return render_template(
        'admin/dashboard.html',
        total_mangas=total_mangas,
        total_chapters=total_chapters,
        total_users=total_users,
        total_comments=total_comments,
        pending_comments=pending_comments,
        pending_reports=pending_reports,
        recent_mangas=recent_mangas,
        recent_users=recent_users,
        recent_logs=recent_logs,
    )


# -------------------------------------------------------------------------
# 2. Catálogo de Mangás
# -------------------------------------------------------------------------
@admin_bp.route('/mangas')
def mangas_list():
    search = request.args.get('q', '').strip()
    status = request.args.get('status', '').strip()
    visibility = request.args.get('visibility', '').strip()
    page = request.args.get('page', 1, type=int)

    pagination = list_admin_mangas(
        search=search or None,
        status=status or None,
        visibility=visibility if visibility != '' else None,
        page=page,
        per_page=12,
    )

    return render_template(
        'admin/mangas/list.html',
        pagination=pagination,
        search=search,
        status=status,
        visibility=visibility,
    )


@admin_bp.route('/mangas/new', methods=['GET', 'POST'])
def manga_new():
    form = MangaForm()

    if form.validate_on_submit():
        anilist_id = form.anilist_id.data

        # Verificar duplicidade pelo anilist_id
        if anilist_id:
            duplicate = Manga.query.filter_by(anilist_id=anilist_id).first()
            if duplicate:
                flash(
                    f"A obra com ID AniList {anilist_id} ('{duplicate.title}') já está cadastrada no catálogo. "
                    f"Você pode editá-la diretamente.",
                    'warning',
                )
                return redirect(url_for('admin.manga_edit', manga_id=duplicate.id))

        banner_url = (form.banner_image.data or '').strip() or None

        # Processamento de Upload de Banner Local
        if form.banner_file.data and form.banner_file.data.filename:
            file = form.banner_file.data
            safe_name = secure_filename(file.filename)
            ext = safe_name.rsplit('.', 1)[-1].lower() if '.' in safe_name else 'jpg'
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"banner_{timestamp}_{safe_name}"

            upload_dir = Path(current_app.root_path) / 'static' / 'uploads' / 'banners'
            upload_dir.mkdir(parents=True, exist_ok=True)
            file_path = upload_dir / filename
            file.save(str(file_path))
            banner_url = url_for('static', filename=f"uploads/banners/{filename}")

        manga = Manga(
            title=form.title.data.strip(),
            alternative_titles=(form.alternative_titles.data or '').strip() or None,
            anilist_id=anilist_id,
            synopsis=(form.synopsis.data or '').strip() or None,
            cover_image=(form.cover_image.data or '').strip() or None,
            banner_image=banner_url,
            banner_position=form.banner_position.data or 'center',
            genres=(form.genres.data or '').strip() or None,
            author=(form.author.data or '').strip() or None,
            publication_status=form.publication_status.data,
            anilist_chapters=form.anilist_chapters.data,
            start_date=(form.start_date.data or '').strip() or None,
            end_date=(form.end_date.data or '').strip() or None,
            is_visible=form.is_visible.data,
            is_featured=form.is_featured.data,
        )
        db.session.add(manga)
        db.session.commit()

        log_action(
            admin_id=current_user.id,
            action='manga_created',
            entity_type='manga',
            entity_id=manga.id,
            description=f"Cadastrou o mangá '{manga.title}' (AniList ID: {manga.anilist_id or 'N/A'}).",
        )

        flash(f"Mangá '{manga.title}' cadastrado com sucesso!", 'success')
        return redirect(url_for('admin.mangas_list'))

    return render_template('admin/mangas/new.html', form=form)


@admin_bp.route('/mangas/api/search-anilist')
def api_search_anilist():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'results': [], 'error': None})

    results, error = get_manga_search_results(query, page=1)
    if error or not results:
        return jsonify({'results': [], 'error': error or 'Nenhum resultado encontrado.'})

    formatted = []
    for item in results:
        title_obj = item.get('title') or {}
        cover_obj = item.get('coverImage') or {}
        title = title_obj.get('romaji') or title_obj.get('english') or title_obj.get('native') or 'Sem título'
        cover = cover_obj.get('large') or cover_obj.get('extraLarge') or ''
        formatted.append({
            'id': item.get('id'),
            'title': title,
            'cover': cover,
            'status': item.get('status') or 'UNKNOWN',
            'chapters': item.get('chapters') or 'N/A',
            'averageScore': item.get('averageScore') or 'N/A',
        })

    return jsonify({'results': formatted, 'error': None})


@admin_bp.route('/mangas/api/anilist-details/<int:anilist_id>')
def api_anilist_details(anilist_id):
    media, error = get_manga_by_id(anilist_id)
    if error or not media:
        return jsonify({'error': error or 'Detalhes não encontrados na AniList.'}), 404

    title_obj = media.get('title') or {}
    cover_obj = media.get('coverImage') or {}
    primary_title = title_obj.get('romaji') or title_obj.get('english') or title_obj.get('native') or ''

    alt_titles = []
    for k in ('english', 'native', 'romaji'):
        v = title_obj.get(k)
        if v and v != primary_title and v not in alt_titles:
            alt_titles.append(v)

    # Autores do staff
    authors = []
    staff_edges = (media.get('staff') or {}).get('edges') or []
    for edge in staff_edges:
        role = (edge.get('role') or '').casefold()
        if 'story' in role or 'art' in role or 'original' in role or not authors:
            name = ((edge.get('node') or {}).get('name') or {}).get('full')
            if name and name not in authors:
                authors.append(name)

    # Datas
    start_obj = media.get('startDate') or {}
    start_date = ''
    if start_obj.get('year'):
        y, m, d = start_obj.get('year'), start_obj.get('month') or 1, start_obj.get('day') or 1
        start_date = f'{y:04d}-{m:02d}-{d:02d}'

    # Buscar sinopse em Português via MangaDex (com fallback de tradução)
    from app.services.mangadex_service import fetch_portuguese_synopsis
    raw_desc = media.get('description') or ''
    clean_synopsis = fetch_portuguese_synopsis(primary_title, fallback_english_synopsis=raw_desc)

    cover_extra_large = cover_obj.get('extraLarge') or ''
    cover_large = cover_obj.get('large') or ''
    banner_img = media.get('bannerImage') or ''

    from app.services.mangadex_service import get_mangadex_chapter_count

    anilist_ch = media.get('chapters')
    if not anilist_ch:
        # Tenta fallback via MangaDex pelo título principal
        md_ch = get_mangadex_chapter_count(primary_title)
        if md_ch:
            anilist_ch = md_ch

    payload = {
        'anilist_id': media.get('id'),
        'title': primary_title,
        'alternative_titles': ' | '.join(alt_titles),
        'synopsis': clean_synopsis,
        'cover_image': cover_extra_large or cover_large or '',
        'cover_image_extra_large': cover_extra_large,
        'cover_image_large': cover_large,
        'banner_image': banner_img,
        'genres': ', '.join(media.get('genres') or []),
        'author': ', '.join(authors[:3]) if authors else '',
        'publication_status': media.get('status') or 'RELEASING',
        'anilist_chapters': anilist_ch,
        'start_date': start_date,
    }
    return jsonify({'manga': payload, 'error': None})


@admin_bp.route('/mangas/api/translate-text', methods=['POST'])
def api_translate_text():
    data = request.get_json(silent=True) or {}
    text = data.get('text', '')
    title = data.get('title', '')
    if not text or not text.strip():
        return jsonify({'error': 'Nenhum texto informado para tradução.', 'translated': ''}), 400

    try:
        from app.services.mangadex_service import fetch_portuguese_synopsis
        if title:
            translated = fetch_portuguese_synopsis(title=title, fallback_english_synopsis=text)
        else:
            translated = translate_text_to_portuguese(text)
        return jsonify({'translated': translated, 'error': None})
    except Exception as err:
        return jsonify({'error': f'Falha ao obter sinopse em português: {err}', 'translated': clean_html_tags(text)}), 500


@admin_bp.route('/mangas/<int:manga_id>/update-synopsis-pt', methods=['POST'])
def manga_update_synopsis_pt(manga_id):
    manga = Manga.query.get_or_404(manga_id)
    from app.services.mangadex_service import fetch_portuguese_synopsis
    
    synopsis_pt = fetch_portuguese_synopsis(manga.title, fallback_english_synopsis=manga.synopsis)
    if not synopsis_pt or not synopsis_pt.strip():
        flash(f"Não foi possível localizar sinopse em português para '{manga.title}'.", 'warning')
        return redirect(request.referrer or url_for('admin.manga_edit', manga_id=manga.id))

    manga.synopsis = synopsis_pt
    db.session.commit()

    log_action(
        admin_id=current_user.id,
        action='manga_synopsis_updated_pt',
        entity_type='manga',
        entity_id=manga.id,
        description=f"Atualizou a sinopse do mangá '{manga.title}' para Português (MangaDex/Tradução).",
    )

    flash(f"Sinopse de '{manga.title}' atualizada com sucesso para Português!", 'success')
    return redirect(request.referrer or url_for('admin.manga_edit', manga_id=manga.id))


@admin_bp.route('/mangas/batch-update-synopses-pt', methods=['POST'])
def mangas_batch_update_synopses_pt():
    from app.services.mangadex_service import fetch_portuguese_synopsis
    mangas = Manga.query.all()
    updated_count = 0

    for m in mangas:
        # Busca sinopse oficial na MangaDex ou traduz
        pt_synopsis = fetch_portuguese_synopsis(m.title, fallback_english_synopsis=m.synopsis)
        if pt_synopsis and pt_synopsis.strip() and pt_synopsis != m.synopsis:
            m.synopsis = pt_synopsis
            updated_count += 1

    if updated_count > 0:
        db.session.commit()
        log_action(
            admin_id=current_user.id,
            action='mangas_batch_synopsis_updated_pt',
            entity_type='manga',
            entity_id=None,
            description=f"Atualizou sinopses em lote para Português em {updated_count} obras.",
        )
        flash(f"{updated_count} obra(s) tiveram suas sinopses atualizadas para Português com sucesso!", 'success')
    else:
        flash('Nenhuma sinopse precisou de atualização ou todas já estão em Português.', 'info')

    return redirect(request.referrer or url_for('admin.mangas_list'))


@admin_bp.route('/mangas/<int:manga_id>/translate-synopsis', methods=['POST'])
def manga_translate_synopsis(manga_id):
    return manga_update_synopsis_pt(manga_id)



@admin_bp.route('/mangas/<int:manga_id>/edit', methods=['GET', 'POST'])
def manga_edit(manga_id):
    manga = Manga.query.get_or_404(manga_id)
    form = MangaForm(obj=manga)

    if form.validate_on_submit():
        manga.title = form.title.data.strip()
        manga.alternative_titles = (form.alternative_titles.data or '').strip() or None
        manga.synopsis = (form.synopsis.data or '').strip() or None
        manga.cover_image = (form.cover_image.data or '').strip() or None
        # Processamento de Upload de Banner Local
        banner_url = (form.banner_image.data or '').strip() or None
        if form.banner_file.data and form.banner_file.data.filename:
            file = form.banner_file.data
            safe_name = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"banner_{timestamp}_{safe_name}"

            upload_dir = Path(current_app.root_path) / 'static' / 'uploads' / 'banners'
            upload_dir.mkdir(parents=True, exist_ok=True)
            file_path = upload_dir / filename
            file.save(str(file_path))
            banner_url = url_for('static', filename=f"uploads/banners/{filename}")

        manga.banner_image = banner_url
        manga.banner_position = form.banner_position.data or 'center'
        manga.genres = (form.genres.data or '').strip() or None
        manga.author = (form.author.data or '').strip() or None
        manga.publication_status = form.publication_status.data
        manga.anilist_chapters = form.anilist_chapters.data
        manga.start_date = (form.start_date.data or '').strip() or None
        manga.end_date = (form.end_date.data or '').strip() or None
        manga.is_visible = form.is_visible.data
        manga.is_featured = form.is_featured.data

        db.session.commit()

        log_action(
            admin_id=current_user.id,
            action='manga_updated',
            entity_type='manga',
            entity_id=manga.id,
            description=f"Atualizou dados do mangá '{manga.title}'.",
        )

        flash(f"Mangá '{manga.title}' atualizado com sucesso!", 'success')
        return redirect(url_for('admin.mangas_list'))

    return render_template('admin/mangas/edit.html', form=form, manga=manga)


@admin_bp.route('/mangas/<int:manga_id>/toggle-visibility', methods=['POST'])
def manga_toggle_visibility(manga_id):
    manga = Manga.query.get_or_404(manga_id)
    manga.is_visible = not manga.is_visible
    db.session.commit()

    status_str = 'visível no catálogo' if manga.is_visible else 'oculto'
    log_action(
        admin_id=current_user.id,
        action='manga_visibility_toggled',
        entity_type='manga',
        entity_id=manga.id,
        description=f"Alterou visibilidade de '{manga.title}' para {status_str}.",
    )
    flash(f"Mangá '{manga.title}' agora está {status_str}.", 'info')
    return redirect(request.referrer or url_for('admin.mangas_list'))


@admin_bp.route('/mangas/<int:manga_id>/toggle-featured', methods=['POST'])
def manga_toggle_featured(manga_id):
    manga = Manga.query.get_or_404(manga_id)
    manga.is_featured = not manga.is_featured
    db.session.commit()

    destaque_str = 'em destaque' if manga.is_featured else 'sem destaque'
    log_action(
        admin_id=current_user.id,
        action='manga_featured_toggled',
        entity_type='manga',
        entity_id=manga.id,
        description=f"Marcou mangá '{manga.title}' como {destaque_str}.",
    )
    flash(f"Mangá '{manga.title}' definido como {destaque_str}.", 'info')
    return redirect(request.referrer or url_for('admin.mangas_list'))


@admin_bp.route('/mangas/<int:manga_id>/delete', methods=['POST'])
def manga_delete(manga_id):
    manga = Manga.query.get_or_404(manga_id)
    title = manga.title
    chapters_count = len(manga.chapters)

    delete_manga_safely(manga)

    log_action(
        admin_id=current_user.id,
        action='manga_deleted',
        entity_type='manga',
        entity_id=manga_id,
        description=f"Excluiu o mangá '{title}' e seus {chapters_count} capítulos vinculados.",
    )

    flash(f"Mangá '{title}' e seus capítulos foram excluídos com sucesso.", 'success')
    return redirect(url_for('admin.mangas_list'))


# -------------------------------------------------------------------------
# 3. Capítulos e Upload de PDF
# -------------------------------------------------------------------------
@admin_bp.route('/chapters')
def chapters_list():
    manga_id = request.args.get('manga_id', type=int)
    search = request.args.get('q', '').strip()
    status = request.args.get('status', '').strip()
    file_type = request.args.get('file_type', '').strip()
    page = request.args.get('page', 1, type=int)

    query = Chapter.query
    if manga_id:
        query = query.filter((Chapter.manga_id == manga_id) | (Chapter.anilist_id == manga_id))
    if search:
        search_term = f'%{search}%'
        query = query.filter(
            or_(
                Chapter.chapter_title.ilike(search_term),
                Chapter.original_filename.ilike(search_term),
            )
        )
    if status:
        query = query.filter(Chapter.status == status)
    if file_type:
        query = query.filter(Chapter.file_type == file_type)

    pagination = query.order_by(Chapter.created_at.desc()).paginate(page=page, per_page=15, error_out=False)
    mangas = Manga.query.order_by(Manga.title.asc()).all()

    return render_template(
        'admin/chapters/list.html',
        pagination=pagination,
        mangas=mangas,
        selected_manga_id=manga_id,
        search=search,
        status=status,
        file_type=file_type,
    )


@admin_bp.route('/chapters/new', methods=['GET', 'POST'])
def chapter_new():
    form = ChapterPDFUploadForm()
    mangas = Manga.query.order_by(Manga.title.asc()).all()
    form.manga_id.choices = [(0, '--- Selecione um mangá cadastrado ou informe o ID AniList abaixo ---')] + [
        (m.id, f'{m.title} (AniList: {m.anilist_id or "N/A"})') for m in mangas
    ]

    prefill_manga_id = request.args.get('manga_id', type=int)
    if prefill_manga_id and request.method == 'GET':
        prefill_manga = Manga.query.get(prefill_manga_id)
        if prefill_manga:
            form.manga_id.data = prefill_manga.id
            if prefill_manga.anilist_id:
                form.anilist_id.data = prefill_manga.anilist_id

    if form.validate_on_submit():
        selected_m_id = form.manga_id.data if form.manga_id.data != 0 else None
        anilist_id = form.anilist_id.data

        if selected_m_id and not anilist_id:
            m = Manga.query.get(selected_m_id)
            if m and m.anilist_id:
                anilist_id = m.anilist_id

        try:
            chapter = save_chapter_pdf(
                upload=form.pdf_file.data,
                manga_id=selected_m_id,
                anilist_id=anilist_id,
                chapter_number=form.chapter_number.data,
                chapter_title=form.chapter_title.data,
                volume_number=form.volume_number.data,
                status=form.status.data,
                is_available=form.is_available.data,
                uploaded_by_id=current_user.id,
                authorization_confirmed=form.authorization_confirmed.data,
            )
        except PDFUploadError as err:
            flash(str(err), 'danger')
        else:
            log_action(
                admin_id=current_user.id,
                action='chapter_uploaded_pdf',
                entity_type='chapter',
                entity_id=chapter.id,
                description=f"Fez upload do capítulo {chapter.chapter_number} em PDF (Arquivo: {chapter.original_filename}, Páginas: {chapter.page_count}).",
            )
            flash(
                f'Capítulo {chapter.chapter_number} em PDF importado com sucesso ({chapter.page_count} páginas).',
                'success',
            )
            return redirect(url_for('admin.chapters_list'))

    return render_template('admin/chapters/new.html', form=form, mangas=mangas)


@admin_bp.route('/chapters/<int:chapter_id>/edit', methods=['GET', 'POST'])
def chapter_edit(chapter_id):
    chapter = Chapter.query.get_or_404(chapter_id)
    form = ChapterPDFEditForm(obj=chapter)

    if form.validate_on_submit():
        chapter.chapter_number = form.chapter_number.data
        chapter.chapter_title = (form.chapter_title.data or '').strip() or None
        chapter.volume_number = form.volume_number.data
        chapter.status = form.status.data
        chapter.is_available = form.is_available.data

        # Se houver novo arquivo PDF para substituição
        if form.pdf_file.data and form.pdf_file.data.filename:
            try:
                replace_chapter_pdf(chapter, form.pdf_file.data)
                flash('Arquivo PDF substituído com sucesso.', 'info')
            except PDFUploadError as err:
                flash(f'Erro ao substituir PDF: {err}', 'danger')
                return render_template('admin/chapters/edit.html', form=form, chapter=chapter)

        db.session.commit()

        log_action(
            admin_id=current_user.id,
            action='chapter_updated',
            entity_type='chapter',
            entity_id=chapter.id,
            description=f'Atualizou metadados do capítulo {chapter.chapter_number}.',
        )

        flash(f'Capítulo {chapter.chapter_number} atualizado com sucesso.', 'success')
        return redirect(url_for('admin.chapters_list'))

    return render_template('admin/chapters/edit.html', form=form, chapter=chapter)


@admin_bp.route('/chapters/<int:chapter_id>/delete', methods=['POST'])
def chapter_delete(chapter_id):
    chapter = Chapter.query.get_or_404(chapter_id)
    chap_num = chapter.chapter_number

    if chapter.file_type == 'pdf':
        delete_chapter_file(chapter)
    else:
        from app.services.reader_service import delete_chapter
        delete_chapter(chapter)

    log_action(
        admin_id=current_user.id,
        action='chapter_deleted',
        entity_type='chapter',
        entity_id=chapter_id,
        description=f'Excluiu o capítulo {chap_num} e seus arquivos associados.',
    )

    flash(f'Capítulo {chap_num} excluído com sucesso.', 'success')
    return redirect(url_for('admin.chapters_list'))


@admin_bp.route('/chapters/<int:chapter_id>/pdf')
def serve_chapter_pdf(chapter_id):
    chapter = Chapter.query.get_or_404(chapter_id)
    if chapter.file_type != 'pdf':
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


@admin_bp.route('/chapters/<int:chapter_id>/view')
def chapter_pdf_reader(chapter_id):
    chapter = Chapter.query.get_or_404(chapter_id)
    manga = chapter.manga
    if not manga and chapter.anilist_id:
        manga = Manga.query.filter_by(anilist_id=chapter.anilist_id).first()

    pdf_url = url_for('admin.serve_chapter_pdf', chapter_id=chapter.id)
    return render_template('admin/chapters/reader_pdf.html', chapter=chapter, manga=manga, pdf_url=pdf_url)


# -------------------------------------------------------------------------
# 4. Gerenciamento de Usuários
# -------------------------------------------------------------------------
@admin_bp.route('/users')
def users_list():
    search = request.args.get('q', '').strip()
    role = request.args.get('role', '').strip()
    status = request.args.get('status', '').strip()
    page = request.args.get('page', 1, type=int)

    query = User.query
    if search:
        search_term = f'%{search}%'
        query = query.filter(or_(User.name.ilike(search_term), User.email.ilike(search_term)))
    if role:
        if role == 'admin':
            query = query.filter(User.is_admin == True)
        elif role == 'user':
            query = query.filter(User.is_admin == False)
    if status:
        if status == 'active':
            query = query.filter(User.is_active == True)
        elif status == 'blocked':
            query = query.filter(User.is_active == False)

    pagination = query.order_by(User.created_at.desc()).paginate(page=page, per_page=15, error_out=False)

    return render_template(
        'admin/users/list.html',
        pagination=pagination,
        search=search,
        role=role,
        status=status,
    )


@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
def user_edit(user_id):
    user = User.query.get_or_404(user_id)
    form = UserAdminEditForm(obj=user)

    if request.method == 'GET':
        form.role.data = 'admin' if user.is_admin else 'user'
        form.is_active.data = user.is_active

    if form.validate_on_submit():
        new_email = form.email.data.strip().lower()

        # Verificar unicidade do e-mail
        existing_email = User.query.filter(User.email == new_email, User.id != user.id).first()
        if existing_email:
            flash(f"O e-mail '{new_email}' já está em uso por outro usuário.", 'danger')
            return render_template('admin/users/edit.html', form=form, user=user)

        target_is_admin = (form.role.data == 'admin')
        target_is_active = form.is_active.data

        # Proteção: impedir remover a própria permissão de administrador
        if user.id == current_user.id and not target_is_admin:
            flash('Por segurança, você não pode remover sua própria permissão de administrador.', 'danger')
            return render_template('admin/users/edit.html', form=form, user=user)

        # Proteção: impedir rebaixar ou desativar o último administrador ativo
        if user.is_admin and (not target_is_admin or not target_is_active):
            active_admin_count = User.query.filter_by(is_admin=True, is_active=True).count()
            if active_admin_count <= 1:
                flash(
                    'Operação cancelada: Este é o único administrador ativo do sistema. Promova outro administrador antes.',
                    'danger',
                )
                return render_template('admin/users/edit.html', form=form, user=user)

        user.name = form.name.data.strip()
        user.email = new_email
        user.is_admin = target_is_admin
        user.is_active = target_is_active

        if form.new_password.data:
            user.password_hash = generate_password_hash(form.new_password.data)

        db.session.commit()

        log_action(
            admin_id=current_user.id,
            action='user_updated',
            entity_type='user',
            entity_id=user.id,
            description=f"Atualizou o usuário '{user.name}' ({user.email}) - Papel: {user.role}, Ativo: {user.is_active}.",
        )

        flash(f"Usuário '{user.name}' atualizado com sucesso.", 'success')
        return redirect(url_for('admin.users_list'))

    return render_template('admin/users/edit.html', form=form, user=user)


@admin_bp.route('/users/<int:user_id>/toggle-status', methods=['POST'])
def user_toggle_status(user_id):
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash('Você não pode bloquear sua própria conta.', 'warning')
        return redirect(request.referrer or url_for('admin.users_list'))

    if user.is_admin and user.is_active:
        active_admin_count = User.query.filter_by(is_admin=True, is_active=True).count()
        if active_admin_count <= 1:
            flash('Você não pode bloquear o único administrador ativo do sistema.', 'danger')
            return redirect(request.referrer or url_for('admin.users_list'))

    user.is_active = not user.is_active
    db.session.commit()

    action_label = 'desbloqueado' if user.is_active else 'bloqueado'
    log_action(
        admin_id=current_user.id,
        action='user_status_toggled',
        entity_type='user',
        entity_id=user.id,
        description=f"Usuário '{user.name}' ({user.email}) foi {action_label}.",
    )

    flash(f"Usuário '{user.name}' foi {action_label}.", 'info')
    return redirect(request.referrer or url_for('admin.users_list'))


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
def user_delete(user_id):
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash('Você não pode excluir sua própria conta nesta tela.', 'warning')
        return redirect(request.referrer or url_for('admin.users_list'))

    if user.is_admin:
        active_admin_count = User.query.filter_by(is_admin=True, is_active=True).count()
        if active_admin_count <= 1:
            flash('Não é possível excluir o único administrador ativo.', 'danger')
            return redirect(request.referrer or url_for('admin.users_list'))

    name = user.name
    email = user.email
    db.session.delete(user)
    db.session.commit()

    log_action(
        admin_id=current_user.id,
        action='user_deleted',
        entity_type='user',
        entity_id=user_id,
        description=f"Excluiu o usuário '{name}' ({email}).",
    )

    flash(f"Usuário '{name}' excluído com sucesso.", 'success')
    return redirect(url_for('admin.users_list'))


# -------------------------------------------------------------------------
# 5. Moderação de Comentários e Denúncias
# -------------------------------------------------------------------------
@admin_bp.route('/comments')
def comments_list():
    search = request.args.get('q', '').strip()
    status = request.args.get('status', '').strip()
    page = request.args.get('page', 1, type=int)

    query = Comment.query
    if search:
        query = query.filter(Comment.content.ilike(f'%{search}%'))
    if status:
        query = query.filter(Comment.status == status)

    pagination = query.order_by(Comment.created_at.desc()).paginate(page=page, per_page=15, error_out=False)

    return render_template(
        'admin/comments/list.html',
        pagination=pagination,
        search=search,
        status=status,
    )


@admin_bp.route('/comments/<int:comment_id>/hide', methods=['POST'])
def comment_hide(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    comment.status = 'hidden'
    db.session.commit()

    log_action(
        admin_id=current_user.id,
        action='comment_hidden',
        entity_type='comment',
        entity_id=comment.id,
        description=f"Ocultou comentário #{comment.id} do usuário '{comment.user.name}'.",
    )

    flash('Comentário ocultado do público com sucesso.', 'info')
    return redirect(request.referrer or url_for('admin.comments_list'))


@admin_bp.route('/comments/<int:comment_id>/restore', methods=['POST'])
def comment_restore(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    comment.status = 'published'
    db.session.commit()

    log_action(
        admin_id=current_user.id,
        action='comment_restored',
        entity_type='comment',
        entity_id=comment.id,
        description=f"Restaurou comentário #{comment.id} para publicado.",
    )

    flash('Comentário restaurado para visualização pública.', 'success')
    return redirect(request.referrer or url_for('admin.comments_list'))


@admin_bp.route('/comments/<int:comment_id>/delete', methods=['POST'])
def comment_delete(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    c_id = comment.id
    user_name = comment.user.name if comment.user else 'Usuário desconhecido'
    db.session.delete(comment)
    db.session.commit()

    log_action(
        admin_id=current_user.id,
        action='comment_deleted',
        entity_type='comment',
        entity_id=c_id,
        description=f"Excluiu permanentemente o comentário #{c_id} de '{user_name}'.",
    )

    flash('Comentário excluído permanentemente.', 'success')
    return redirect(request.referrer or url_for('admin.comments_list'))


# -------------------------------------------------------------------------
# 6. Módulo de Relatórios Administrativos e Exportações (PDF & CSV)
# -------------------------------------------------------------------------
@admin_bp.route('/reports')
@admin_bp.route('/relatorios')
def admin_reports():
    tab = request.args.get('tab', 'users').strip()
    if tab not in ('users', 'mangas'):
        tab = 'users'

    # Filtros de Usuários
    user_role = request.args.get('role', '').strip()
    user_status = request.args.get('status', '').strip()
    user_date_start = request.args.get('date_start', '').strip()
    user_date_end = request.args.get('date_end', '').strip()

    # Filtros de Mangás
    manga_status = request.args.get('publication_status', '').strip()
    manga_visibility = request.args.get('visibility', '').strip()
    manga_featured = request.args.get('is_featured', '').strip()
    manga_date_start = request.args.get('manga_date_start', '').strip()
    manga_date_end = request.args.get('manga_date_end', '').strip()

    users_data = get_users_report_data(
        role=user_role,
        status=user_status,
        date_start=user_date_start,
        date_end=user_date_end,
    )

    mangas_data = get_mangas_report_data(
        publication_status=manga_status,
        visibility=manga_visibility,
        is_featured=manga_featured,
        date_start=manga_date_start,
        date_end=manga_date_end,
    )

    return render_template(
        'admin/reports/index.html',
        active_tab=tab,
        users=users_data,
        users_count=len(users_data),
        user_role=user_role,
        user_status=user_status,
        user_date_start=user_date_start,
        user_date_end=user_date_end,
        mangas=mangas_data,
        mangas_count=len(mangas_data),
        manga_status=manga_status,
        manga_visibility=manga_visibility,
        manga_featured=manga_featured,
        manga_date_start=manga_date_start,
        manga_date_end=manga_date_end,
    )


@admin_bp.route('/reports/export/csv')
@admin_bp.route('/reports/<report_type>/export/csv')
def export_reports_csv(report_type=None):
    if not report_type:
        report_type = request.args.get('type', 'users').strip()

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    if report_type == 'users':
        role = request.args.get('role', '').strip()
        status = request.args.get('status', '').strip()
        date_start = request.args.get('date_start', '').strip()
        date_end = request.args.get('date_end', '').strip()

        users = get_users_report_data(role, status, date_start, date_end)
        csv_bytes = generate_users_csv(users)
        filename = f'relatorio_usuarios_{timestamp}.csv'
        log_action(
            admin_id=current_user.id,
            action='report_exported_csv',
            entity_type='report',
            description=f"Exportou relatório de usuários em CSV ({len(users)} registros).",
        )
    elif report_type == 'mangas':
        pub_status = request.args.get('publication_status', '').strip()
        vis = request.args.get('visibility', '').strip()
        feat = request.args.get('is_featured', '').strip()
        date_start = request.args.get('date_start', request.args.get('manga_date_start', '')).strip()
        date_end = request.args.get('date_end', request.args.get('manga_date_end', '')).strip()

        mangas = get_mangas_report_data(pub_status, vis, feat, date_start, date_end)
        csv_bytes = generate_mangas_csv(mangas)
        filename = f'relatorio_mangas_{timestamp}.csv'
        log_action(
            admin_id=current_user.id,
            action='report_exported_csv',
            entity_type='report',
            description=f"Exportou relatório de mangás em CSV ({len(mangas)} registros).",
        )
    else:
        abort(400)

    response = Response(csv_bytes, mimetype='text/csv; charset=utf-8')
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@admin_bp.route('/reports/export/pdf')
@admin_bp.route('/reports/<report_type>/export/pdf')
def export_reports_pdf(report_type=None):
    if not report_type:
        report_type = request.args.get('type', 'users').strip()

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    admin_name = current_user.name if current_user and hasattr(current_user, 'name') else 'Administrador'

    if report_type == 'users':
        role = request.args.get('role', '').strip()
        status = request.args.get('status', '').strip()
        date_start = request.args.get('date_start', '').strip()
        date_end = request.args.get('date_end', '').strip()

        users = get_users_report_data(role, status, date_start, date_end)
        filters_dict = {
            'role': role,
            'status': status,
            'date_start': date_start,
            'date_end': date_end,
        }
        pdf_bytes = generate_users_pdf(users, filters_dict, admin_name)
        filename = f'relatorio_usuarios_{timestamp}.pdf'
        log_action(
            admin_id=current_user.id,
            action='report_exported_pdf',
            entity_type='report',
            description=f"Exportou relatório de usuários em PDF ({len(users)} registros).",
        )
    elif report_type == 'mangas':
        pub_status = request.args.get('publication_status', '').strip()
        vis = request.args.get('visibility', '').strip()
        feat = request.args.get('is_featured', '').strip()
        date_start = request.args.get('date_start', request.args.get('manga_date_start', '')).strip()
        date_end = request.args.get('date_end', request.args.get('manga_date_end', '')).strip()

        mangas = get_mangas_report_data(pub_status, vis, feat, date_start, date_end)
        filters_dict = {
            'publication_status': pub_status,
            'visibility': vis,
            'is_featured': feat,
            'date_start': date_start,
            'date_end': date_end,
        }
        pdf_bytes = generate_mangas_pdf(mangas, filters_dict, admin_name)
        filename = f'relatorio_mangas_{timestamp}.pdf'
        log_action(
            admin_id=current_user.id,
            action='report_exported_pdf',
            entity_type='report',
            description=f"Exportou relatório de mangás em PDF ({len(mangas)} registros).",
        )
    else:
        abort(400)

    response = Response(pdf_bytes, mimetype='application/pdf')
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# -------------------------------------------------------------------------
# Denúncias de Comentários
# -------------------------------------------------------------------------
@admin_bp.route('/denuncias')
@admin_bp.route('/comments/reports')
def reports_list():
    status = request.args.get('status', '').strip()
    page = request.args.get('page', 1, type=int)

    query = CommentReport.query
    if status:
        query = query.filter(CommentReport.status == status)

    pagination = query.order_by(CommentReport.created_at.desc()).paginate(page=page, per_page=15, error_out=False)

    return render_template(
        'admin/comments/reports.html',
        pagination=pagination,
        status=status,
    )


@admin_bp.route('/reports/<int:report_id>/<action>', methods=['POST'])
@admin_bp.route('/denuncias/<int:report_id>/<action>', methods=['POST'])
def report_action(report_id, action):
    report = CommentReport.query.get_or_404(report_id)

    valid_actions = {
        'resolve': 'resolved',
        'dismiss': 'dismissed',
        'review': 'under_review',
    }
    if action not in valid_actions:
        abort(400)

    report.status = valid_actions[action]
    db.session.commit()

    labels = {
        'resolved': 'resolvida',
        'dismissed': 'ignorada',
        'under_review': 'em análise',
    }

    log_action(
        admin_id=current_user.id,
        action=f'report_{action}',
        entity_type='comment_report',
        entity_id=report.id,
        description=f"Marcou denúncia #{report.id} como {labels[report.status]}.",
    )

    flash(f"Denúncia marcada como {labels[report.status]}.", 'info')
    return redirect(request.referrer or url_for('admin.reports_list'))


# -------------------------------------------------------------------------
# 6. Registro de Atividades Administrativas (Logs)
# -------------------------------------------------------------------------
@admin_bp.route('/logs')
def logs_list():
    search = request.args.get('q', '').strip()
    entity_type = request.args.get('entity', '').strip()
    page = request.args.get('page', 1, type=int)

    query = AdminLog.query
    if search:
        query = query.filter(
            or_(
                AdminLog.description.ilike(f'%{search}%'),
                AdminLog.action.ilike(f'%{search}%'),
            )
        )
    if entity_type:
        query = query.filter(AdminLog.entity_type == entity_type)

    pagination = query.order_by(AdminLog.created_at.desc()).paginate(page=page, per_page=20, error_out=False)

    return render_template(
        'admin/logs/list.html',
        pagination=pagination,
        search=search,
        entity_type=entity_type,
    )
