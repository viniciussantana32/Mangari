from app.extensions import db
from app.models.chapter import Chapter
from app.models.comment import Comment
from app.models.manga import Manga


def get_admin_manga_stats():
    """
    Retorna contagens e dados consolidados para o dashboard.
    """
    total_mangas = Manga.query.count()
    total_chapters = Chapter.query.count()
    return total_mangas, total_chapters


def list_admin_mangas(search=None, status=None, visibility=None, page=1, per_page=15):
    """
    Consulta paginada e filtrada de mangás para a área administrativa.
    """
    query = Manga.query
    if search:
        search_term = f'%{search.strip()}%'
        query = query.filter(
            (Manga.title.ilike(search_term)) |
            (Manga.author.ilike(search_term)) |
            (Manga.genres.ilike(search_term))
        )
    if status:
        query = query.filter(Manga.publication_status == status)
    if visibility is not None and visibility != '':
        is_vis = str(visibility).lower() in ('1', 'true', 'yes')
        query = query.filter(Manga.is_visible == is_vis)

    return query.order_by(Manga.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)


def delete_manga_safely(manga):
    """
    Exclui um mangá preservando integridade ou levantando aviso caso possua capítulos vinculados.
    """
    from app.services.pdf_service import delete_chapter_file
    from app.services.reader_service import delete_chapter as delete_archive_chapter

    # Excluir capítulos associados
    for chapter in list(manga.chapters):
        if chapter.file_type == 'pdf':
            delete_chapter_file(chapter)
        else:
            try:
                delete_archive_chapter(chapter)
            except Exception:
                db.session.delete(chapter)

    # Excluir comentários associados
    for comment in list(manga.comments):
        db.session.delete(comment)

    db.session.delete(manga)
    db.session.commit()
