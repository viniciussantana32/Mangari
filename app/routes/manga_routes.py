from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models.chapter import Chapter
from app.models.comment import Comment
from app.models.comment_report import CommentReport
from app.models.manga import Manga
from app.models.reading_progress import ReadingProgress
from app.services.anilist_service import (
    get_manga_by_id,
    get_manga_search_results,
    get_popular_manga,
)
from app.services.mangadex_service import get_mangadex_chapter_count
from app.services.comment_service import create_comment, get_published_comments, report_comment
from app.services.reader_service import list_chapters

manga_bp = Blueprint('manga', __name__, url_prefix='/manga')


GENRE_MAP = [
    {'slug': 'Action', 'label': 'Ação'},
    {'slug': 'Adventure', 'label': 'Aventura'},
    {'slug': 'Fantasy', 'label': 'Fantasia'},
    {'slug': 'Drama', 'label': 'Drama'},
    {'slug': 'Romance', 'label': 'Romance'},
    {'slug': 'Comedy', 'label': 'Comédia'},
    {'slug': 'Horror', 'label': 'Terror'},
    {'slug': 'Sci-Fi', 'label': 'Ficção Científica'},
    {'slug': 'Mystery', 'label': 'Mistério'},
    {'slug': 'Supernatural', 'label': 'Sobrenatural'},
    {'slug': 'Slice of Life', 'label': 'Cotidiano'},
    {'slug': 'Sports', 'label': 'Esportes'},
]


@manga_bp.route('', methods=['GET'])
@manga_bp.route('/', methods=['GET'])
def catalog():
    query = request.args.get('q', '').strip()
    selected_genre = request.args.get('genre', '').strip()

    if query:
        results, error = get_manga_search_results(query, genre=selected_genre or None)
    elif selected_genre:
        results, error = get_popular_manga(genre=selected_genre, per_page=40)
    else:
        results, error = get_popular_manga(per_page=40)

    # Mangás cadastrados localmente visíveis (com filtro por gênero se houver)
    local_query = Manga.query.filter_by(is_visible=True)
    if selected_genre:
        local_query = local_query.filter(Manga.genres.ilike(f'%{selected_genre}%'))
    local_mangas = local_query.order_by(Manga.created_at.desc()).all()

    return render_template(
        'manga/catalog.html',
        results=results,
        error=error,
        query=query,
        selected_genre=selected_genre,
        genre_list=GENRE_MAP,
        local_mangas=local_mangas,
    )


@manga_bp.route('/<int:manga_id>', methods=['GET'])
def detail(manga_id):
    manga, error = get_manga_by_id(manga_id)
    local_manga = Manga.query.filter_by(anilist_id=manga_id).first()

    # Buscar capítulos locais disponíveis
    query = Chapter.query.filter(Chapter.is_available.is_(True))
    if local_manga:
        query = query.filter((Chapter.anilist_id == manga_id) | (Chapter.manga_id == local_manga.id))
    else:
        query = query.filter(Chapter.anilist_id == manga_id)
    chapters = query.order_by(Chapter.chapter_number.asc()).all()

    # 1. Determinar total de capítulos conhecidos da obra
    total_chapters_known = None
    if manga and manga.get('chapters'):
        try:
            total_chapters_known = int(manga['chapters'])
        except (ValueError, TypeError):
            pass

    if not total_chapters_known and local_manga:
        total_chapters_known = local_manga.total_chapters

    # Fallback MangaDex: se ainda não sabemos o total (AniList retornou null para RELEASING),
    # consulta o MangaDex pelo título da obra e persiste no banco se houver local_manga
    if not total_chapters_known:
        search_title = None
        if manga and manga.get('title'):
            search_title = manga['title'].get('romaji') or manga['title'].get('english') or manga['title'].get('native')
        elif local_manga:
            search_title = local_manga.title

        if search_title:
            md_total = get_mangadex_chapter_count(search_title)
            if md_total and md_total > 0:
                total_chapters_known = md_total
                if local_manga and not local_manga.anilist_chapters:
                    try:
                        local_manga.anilist_chapters = md_total
                        db.session.commit()
                    except Exception:
                        db.session.rollback()

    max_local_ch = 0
    for ch in chapters:
        try:
            num = int(float(ch.chapter_number))
            if num > max_local_ch:
                max_local_ch = num
        except (ValueError, TypeError):
            pass

    if not total_chapters_known and max_local_ch > 0:
        total_chapters_known = max_local_ch

    # 2. Mapeamento de capítulos locais existentes para cruzamento
    local_chapters_map = {}
    for ch in chapters:
        ch_num = float(ch.chapter_number)
        if ch_num.is_integer():
            local_chapters_map[int(ch_num)] = ch
        num_str = f"{ch.chapter_number.normalize():f}" if hasattr(ch.chapter_number, 'normalize') else str(ch.chapter_number)
        local_chapters_map[num_str] = ch

    # 3. Geração da lista unificada cobrindo todos os capítulos
    unified_chapters = []
    covered_ids = set()
    max_iter = total_chapters_known if (total_chapters_known and total_chapters_known > 0) else max_local_ch

    if max_iter > 0:
        for i in range(1, max_iter + 1):
            ch = local_chapters_map.get(i)
            if ch:
                covered_ids.add(ch.id)
                num_str = f"{ch.chapter_number.normalize():f}" if hasattr(ch.chapter_number, 'normalize') else str(ch.chapter_number)
                unified_chapters.append({
                    'number': num_str,
                    'numeric_sort': float(ch.chapter_number),
                    'title': ch.chapter_title or f"Capítulo {num_str}",
                    'volume': ch.volume_number,
                    'published_at': ch.created_at.strftime('%d/%m/%Y') if ch.created_at else None,
                    'is_available': True,
                    'chapter_id': ch.id,
                    'read_url': url_for('reader.read_chapter', chapter_id=ch.id),
                })
            else:
                unified_chapters.append({
                    'number': str(i),
                    'numeric_sort': float(i),
                    'title': f"Capítulo {i}",
                    'volume': None,
                    'published_at': None,
                    'is_available': False,
                    'chapter_id': None,
                    'read_url': None,
                })

    # Adicionar capítulos locais especiais (ex: 1.5, 0.5) não cobertos pelo range inteiro
    for ch in chapters:
        if ch.id not in covered_ids:
            num_str = f"{ch.chapter_number.normalize():f}" if hasattr(ch.chapter_number, 'normalize') else str(ch.chapter_number)
            unified_chapters.append({
                'number': num_str,
                'numeric_sort': float(ch.chapter_number),
                'title': ch.chapter_title or f"Capítulo {num_str}",
                'volume': ch.volume_number,
                'published_at': ch.created_at.strftime('%d/%m/%Y') if ch.created_at else None,
                'is_available': True,
                'chapter_id': ch.id,
                'read_url': url_for('reader.read_chapter', chapter_id=ch.id),
            })

    unified_chapters.sort(key=lambda x: x['numeric_sort'])
    available_chapters_count = sum(1 for c in unified_chapters if c['is_available'])
    first_available_chapter = next((c for c in unified_chapters if c['is_available']), None)

    # 4. Continuação de leitura para usuário autenticado
    library_entry = None
    resume_chapter = None

    if current_user.is_authenticated and (manga or local_manga):
        from app.models.library_entry import LibraryEntry

        library_entry = LibraryEntry.query.filter_by(
            user_id=current_user.id,
            anilist_id=manga_id,
        ).first()
        if library_entry and library_entry.current_chapter:
            resume_chapter = next(
                (
                    chapter for chapter in chapters
                    if chapter.chapter_number == library_entry.current_chapter
                ),
                None,
            )
        if resume_chapter is None:
            progress = (
                ReadingProgress.query.join(Chapter)
                .filter(
                    ReadingProgress.user_id == current_user.id,
                    Chapter.anilist_id == manga_id,
                )
                .order_by(ReadingProgress.updated_at.desc())
                .first()
            )
            if progress:
                resume_chapter = progress.chapter

    # Carregar comentários publicados
    comments = get_published_comments(manga_id)

    return render_template(
        'manga/detail.html',
        manga=manga,
        local_manga=local_manga,
        error=error,
        local_chapters=chapters,
        unified_chapters=unified_chapters,
        total_chapters_known=total_chapters_known,
        available_chapters_count=available_chapters_count,
        first_available_chapter=first_available_chapter,
        resume_chapter=resume_chapter,
        comments=comments,
    )


@manga_bp.route('/<int:manga_id>/comment', methods=['POST'])
@login_required
def add_comment(manga_id):
    content = request.form.get('content', '').strip()
    if not content:
        flash('O comentário não pode ficar vazio.', 'warning')
        return redirect(url_for('manga.detail', manga_id=manga_id))

    local_manga = Manga.query.filter_by(anilist_id=manga_id).first()
    manga_id_fk = local_manga.id if local_manga else None

    try:
        create_comment(
            user_id=current_user.id,
            anilist_id=manga_id,
            content=content,
            manga_id=manga_id_fk,
        )
        flash('Comentário publicado com sucesso!', 'success')
    except ValueError as err:
        flash(str(err), 'danger')

    return redirect(url_for('manga.detail', manga_id=manga_id))


@manga_bp.route('/comment/<int:comment_id>/delete', methods=['POST'])
@login_required
def delete_comment_user(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    anilist_id = comment.anilist_id

    # Apenas o autor ou administrador pode excluir o comentário pelo site
    if comment.user_id != current_user.id and not current_user.is_admin:
        abort(403)

    db.session.delete(comment)
    db.session.commit()
    flash('Comentário removido.', 'info')
    return redirect(url_for('manga.detail', manga_id=anilist_id))


@manga_bp.route('/comment/<int:comment_id>/report', methods=['POST'])
@login_required
def report_comment_user(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    reason = request.form.get('reason', '').strip()

    if not reason:
        flash('Por favor informe o motivo da denúncia.', 'warning')
        return redirect(url_for('manga.detail', manga_id=comment.anilist_id))

    try:
        report_comment(
            comment_id=comment.id,
            reporter_id=current_user.id,
            reason=reason,
        )
        flash('Denúncia enviada com sucesso para moderação.', 'success')
    except ValueError as err:
        flash(str(err), 'danger')

    return redirect(url_for('manga.detail', manga_id=comment.anilist_id))
