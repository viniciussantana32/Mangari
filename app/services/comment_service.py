from app.extensions import db
from app.models.comment import Comment
from app.models.comment_report import CommentReport
from app.services.anilist_service import sanitize_html_text


def get_published_comments(anilist_id):
    """
    Retorna apenas comentários públicos e publicados para uma obra.
    """
    return (
        Comment.query.filter_by(anilist_id=anilist_id, status='published')
        .order_by(Comment.created_at.desc())
        .all()
    )


def list_comments_admin(search=None, status=None, user_id=None, anilist_id=None, page=1, per_page=15):
    """
    Listagem de comentários para o painel administrativo com filtros e busca.
    """
    query = Comment.query
    if search:
        search_term = f'%{search.strip()}%'
        query = query.filter(Comment.content.ilike(search_term))
    if status:
        query = query.filter(Comment.status == status)
    if user_id:
        query = query.filter(Comment.user_id == user_id)
    if anilist_id:
        query = query.filter(Comment.anilist_id == anilist_id)

    return query.order_by(Comment.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)


def list_reports_admin(status=None, page=1, per_page=15):
    """
    Listagem de denúncias para o painel administrativo.
    """
    query = CommentReport.query
    if status:
        query = query.filter(CommentReport.status == status)
    return query.order_by(CommentReport.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)


def create_comment(user_id, anilist_id, content, manga_id=None):
    clean_content = sanitize_html_text(content or '')
    if not clean_content:
        raise ValueError('O comentário não pode ficar vazio.')
    if len(clean_content) > 2000:
        raise ValueError('O comentário excede o limite de 2000 caracteres.')

    comment = Comment(
        user_id=user_id,
        anilist_id=anilist_id,
        manga_id=manga_id,
        content=clean_content,
        status='published',
    )
    db.session.add(comment)
    db.session.commit()
    return comment


def report_comment(comment_id, reporter_id, reason):
    clean_reason = (reason or '').strip()
    if not clean_reason:
        raise ValueError('O motivo da denúncia é obrigatório.')

    report = CommentReport(
        comment_id=comment_id,
        reporter_id=reporter_id,
        reason=clean_reason,
        status='pending',
    )
    db.session.add(report)
    db.session.commit()
    return report
