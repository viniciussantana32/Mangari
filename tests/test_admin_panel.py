from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

import pytest
from flask.testing import FlaskCliRunner
from werkzeug.datastructures import FileStorage
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models.admin_log import AdminLog
from app.models.chapter import Chapter
from app.models.comment import Comment
from app.models.comment_report import CommentReport
from app.models.manga import Manga
from app.models.user import User

_MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj <</Type /Catalog /Pages 2 0 R>> endobj\n"
    b"2 0 obj <</Type /Pages /Kids [3 0 R] /Count 1>> endobj\n"
    b"3 0 obj <</Type /Page /Parent 2 0 R>> endobj\n"
    b"xref\n0 4\n0000000000 65535 f \n"
    b"trailer <</Size 4 /Root 1 0 R>>\n"
    b"startxref\n140\n%%EOF"
)


def _create_user(app, name, email, is_admin=False, is_active=True):
    with app.app_context():
        user = User(
            name=name,
            email=email.lower().strip(),
            password_hash=generate_password_hash('password123'),
            is_admin=is_admin,
            is_active=is_active,
        )
        db.session.add(user)
        db.session.commit()
        return user.id


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True


# -------------------------------------------------------------------------
# Testes de Autenticação e Permissões Administrativas
# -------------------------------------------------------------------------
def test_admin_access_control(client, app):
    # 1. Usuário não autenticado tentando acessar dashboard deve ser redirecionado para o login
    res = client.get('/admin/dashboard')
    assert res.status_code == 302
    assert '/auth/login' in res.headers['Location']

    # 2. Usuário comum autenticado tentando acessar dashboard deve receber 403 Forbidden
    user_id = _create_user(app, 'Normal User', 'user@example.com', is_admin=False)
    _login(client, user_id)
    res = client.get('/admin/dashboard')
    assert res.status_code == 403

    # 3. Administrador autenticado deve receber 200 OK
    admin_id = _create_user(app, 'Master Admin', 'admin@example.com', is_admin=True)
    _login(client, admin_id)
    res = client.get('/admin/dashboard')
    assert res.status_code == 200
    assert b'Dashboard Geral' in res.data
    assert b'Mang\xc3\xa1s Locais' in res.data


def test_cli_make_admin(app):
    user_id = _create_user(app, 'Promo Target', 'target@example.com', is_admin=False)
    runner = app.test_cli_runner()

    result = runner.invoke(args=['make-admin', 'target@example.com'])
    assert 'promovido a administrador' in result.output

    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.is_admin is True

    # Testar usuário inexistente
    result_not_found = runner.invoke(args=['make-admin', 'naoexiste@example.com'])
    assert 'Erro: Usuário com e-mail' in result_not_found.output


def test_user_blocking_and_last_admin_protection(client, app):
    admin_id = _create_user(app, 'Admin One', 'admin1@example.com', is_admin=True)
    user_id = _create_user(app, 'Regular User', 'regular@example.com', is_admin=False)

    _login(client, admin_id)

    # Bloquear usuário comum
    res = client.post(f'/admin/users/{user_id}/toggle-status', follow_redirects=True)
    assert res.status_code == 200
    assert 'foi bloqueado'.encode() in res.data

    with app.app_context():
        u = db.session.get(User, user_id)
        assert u.is_active is False

    # Tentar logar com o usuário bloqueado
    client.get('/auth/logout')
    login_res = client.post(
        '/auth/login',
        data={'email': 'regular@example.com', 'password': 'password123'},
        follow_redirects=True,
    )
    assert 'Sua conta está desativada ou bloqueada'.encode() in login_res.data

    # Logar novamente como admin e tentar remover o próprio papel de admin (deve ser impedido)
    _login(client, admin_id)
    res_demote_self = client.post(
        f'/admin/users/{admin_id}/edit',
        data={'name': 'Admin One', 'email': 'admin1@example.com', 'role': 'user', 'is_active': 'y'},
        follow_redirects=True,
    )
    assert 'você não pode remover sua própria permissão de administrador'.encode() in res_demote_self.data

    # Tentar excluir a si mesmo
    res_delete_self = client.post(f'/admin/users/{admin_id}/delete', follow_redirects=True)
    assert 'Você não pode excluir sua própria conta'.encode() in res_delete_self.data


# -------------------------------------------------------------------------
# Testes do Catálogo de Mangás
# -------------------------------------------------------------------------
def test_manga_crud_and_duplicate_prevention(client, app):
    admin_id = _create_user(app, 'Admin Manga', 'admin_manga@example.com', is_admin=True)
    _login(client, admin_id)

    # 1. Cadastrar mangá
    res = client.post(
        '/admin/mangas/new',
        data={
            'title': 'Berserk Deluxe',
            'alternative_titles': 'Berserk',
            'anilist_id': '30002',
            'synopsis': 'Guts o espadachim negro.',
            'cover_image': 'https://example.com/berserk.jpg',
            'genres': 'Action, Fantasy',
            'author': 'Kentaro Miura',
            'publication_status': 'FINISHED',
            'anilist_chapters': '364',
            'is_visible': 'y',
            'is_featured': 'y',
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert 'cadastrado com sucesso'.encode() in res.data

    with app.app_context():
        manga = Manga.query.filter_by(anilist_id=30002).first()
        assert manga is not None
        assert manga.title == 'Berserk Deluxe'
        assert manga.is_featured is True
        manga_id = manga.id

    # 2. Impedir cadastro duplicado pelo anilist_id
    res_dup = client.post(
        '/admin/mangas/new',
        data={
            'title': 'Berserk Outro',
            'anilist_id': '30002',
            'publication_status': 'RELEASING',
            'is_visible': 'y',
        },
        follow_redirects=True,
    )
    assert 'já está cadastrada no catálogo'.encode() in res_dup.data

    # 3. Editar mangá
    res_edit = client.post(
        f'/admin/mangas/{manga_id}/edit',
        data={
            'title': 'Berserk - Edição Definitiva',
            'anilist_id': '30002',
            'publication_status': 'FINISHED',
            'is_visible': 'y',
            'is_featured': '',
        },
        follow_redirects=True,
    )
    assert res_edit.status_code == 200
    with app.app_context():
        manga_updated = db.session.get(Manga, manga_id)
        assert manga_updated.title == 'Berserk - Edição Definitiva'
        assert manga_updated.is_featured is False

    # 4. Alternar visibilidade
    client.post(f'/admin/mangas/{manga_id}/toggle-visibility', follow_redirects=True)
    with app.app_context():
        manga_vis = db.session.get(Manga, manga_id)
        assert manga_vis.is_visible is False

    # 5. Excluir mangá
    res_del = client.post(f'/admin/mangas/{manga_id}/delete', follow_redirects=True)
    assert 'excluídos com sucesso'.encode() in res_del.data
    with app.app_context():
        assert db.session.get(Manga, manga_id) is None


# -------------------------------------------------------------------------
# Testes de Upload e Visualização de Capítulos em PDF
# -------------------------------------------------------------------------
def test_chapter_pdf_upload_and_serving(client, app, tmp_path):
    app.config['MANGA_STORAGE_DIR'] = str(tmp_path)
    admin_id = _create_user(app, 'Admin PDF', 'admin_pdf@example.com', is_admin=True)
    _login(client, admin_id)

    # 1. Rejeição de arquivo não-PDF
    bad_file = FileStorage(stream=BytesIO(b'not a pdf content'), filename='chapter.txt')
    res_bad = client.post(
        '/admin/chapters/new',
        data={
            'anilist_id': '99001',
            'chapter_number': '1',
            'pdf_file': bad_file,
            'authorization_confirmed': 'y',
            'is_available': 'y',
            'status': 'published',
        },
        follow_redirects=True,
    )
    assert 'Apenas arquivos com extensão .pdf são aceitos.'.encode() in res_bad.data

    # 2. Upload válido de PDF
    valid_pdf = FileStorage(stream=BytesIO(_MINIMAL_PDF), filename='capitulo_01.pdf', content_type='application/pdf')
    res_ok = client.post(
        '/admin/chapters/new',
        data={
            'anilist_id': '99001',
            'chapter_number': '1',
            'chapter_title': 'O Início',
            'volume_number': '1',
            'pdf_file': valid_pdf,
            'authorization_confirmed': 'y',
            'is_available': 'y',
            'status': 'published',
        },
        follow_redirects=True,
    )
    assert res_ok.status_code == 200
    assert 'importado com sucesso'.encode() in res_ok.data

    with app.app_context():
        chapter = Chapter.query.filter_by(anilist_id=99001, chapter_number=Decimal('1')).first()
        assert chapter is not None
        assert chapter.file_type == 'pdf'
        assert chapter.page_count >= 1
        assert chapter.original_filename == 'capitulo_01.pdf'
        chapter_id = chapter.id

    # 3. Rota de serviço do PDF
    pdf_res = client.get(f'/admin/chapters/{chapter_id}/pdf')
    assert pdf_res.status_code == 200
    assert pdf_res.headers['Content-Type'] == 'application/pdf'
    assert _MINIMAL_PDF in pdf_res.data
    pdf_res.close()

    # 4. Rota pública de leitura do PDF
    read_res = client.get(f'/reader/chapter/{chapter_id}/pdf')
    assert read_res.status_code == 200
    assert 'pdf-viewer-wrapper'.encode() in read_res.data
    read_res.close()

    # 5. Exclusão de capítulo
    del_res = client.post(f'/admin/chapters/{chapter_id}/delete', follow_redirects=True)
    assert 'excluído com sucesso'.encode() in del_res.data
    with app.app_context():
        assert db.session.get(Chapter, chapter_id) is None


# -------------------------------------------------------------------------
# Testes de Comentários e Moderação
# -------------------------------------------------------------------------
def test_comments_and_reports_moderation(client, app):
    admin_id = _create_user(app, 'Admin Comms', 'admin_c@example.com', is_admin=True)
    user_id = _create_user(app, 'Reader Joe', 'joe@example.com', is_admin=False)

    # 1. Usuário comum posta comentário na página do mangá
    _login(client, user_id)
    with patch('app.routes.manga_routes.get_manga_by_id', return_value=({'id': 50001, 'title': {'romaji': 'Solo Leveling'}}, None)):
        res = client.post(
            '/manga/50001/comment',
            data={'content': 'Obra excelente!'},
            follow_redirects=True,
        )
        assert res.status_code == 200
        assert 'Comentário publicado com sucesso!'.encode() in res.data
        assert 'Obra excelente!'.encode() in res.data

    with app.app_context():
        comment = Comment.query.filter_by(anilist_id=50001).first()
        assert comment is not None
        assert comment.content == 'Obra excelente!'
        assert comment.status == 'published'
        comment_id = comment.id

    # 2. Outro usuário denuncia o comentário
    other_user_id = _create_user(app, 'Reporter Ann', 'ann@example.com', is_admin=False)
    _login(client, other_user_id)
    with patch('app.routes.manga_routes.get_manga_by_id', return_value=({'id': 50001, 'title': {'romaji': 'Solo Leveling'}}, None)):
        rep_res = client.post(
            f'/manga/comment/{comment_id}/report',
            data={'reason': 'Possível spoiler sem marcação'},
            follow_redirects=True,
        )
        assert 'Denúncia enviada com sucesso para moderação.'.encode() in rep_res.data

    with app.app_context():
        report = CommentReport.query.filter_by(comment_id=comment_id).first()
        assert report is not None
        assert report.reason == 'Possível spoiler sem marcação'
        assert report.status == 'pending'
        report_id = report.id

    # 3. Administrador visualiza comentários e oculta o comentário
    _login(client, admin_id)
    hide_res = client.post(f'/admin/comments/{comment_id}/hide', follow_redirects=True)
    assert 'Comentário ocultado'.encode() in hide_res.data

    # Verificar que comentário ocultado NÃO aparece na página pública para usuários comuns
    _login(client, user_id)
    with patch('app.routes.manga_routes.get_manga_by_id', return_value=({'id': 50001, 'title': {'romaji': 'Solo Leveling'}}, None)):
        pub_res = client.get('/manga/50001')
        assert 'Obra excelente!'.encode() not in pub_res.data

    # 4. Administrador resolve a denúncia
    _login(client, admin_id)
    res_rep = client.post(f'/admin/reports/{report_id}/resolve', follow_redirects=True)
    assert 'Denúncia marcada como resolvida'.encode() in res_rep.data

    with app.app_context():
        r_after = db.session.get(CommentReport, report_id)
        assert r_after.status == 'resolved'


# -------------------------------------------------------------------------
# Testes de Logs Administrativos
# -------------------------------------------------------------------------
def test_admin_logs_recorded_and_displayed(client, app):
    admin_id = _create_user(app, 'Log Admin', 'log_admin@example.com', is_admin=True)
    _login(client, admin_id)

    # Executar uma ação que gere log
    client.post(
        '/admin/mangas/new',
        data={
            'title': 'Test Log Manga',
            'anilist_id': '88776',
            'publication_status': 'RELEASING',
            'is_visible': 'y',
        },
        follow_redirects=True,
    )

    with app.app_context():
        log = AdminLog.query.filter_by(action='manga_created').first()
        assert log is not None
        assert 'Test Log Manga' in log.description

    # Visualizar tela de logs
    logs_res = client.get('/admin/logs')
    assert logs_res.status_code == 200
    assert 'Test Log Manga'.encode() in logs_res.data
    assert 'manga_created'.encode() in logs_res.data


def test_banner_selector_api_and_persistence(client, app):
    admin_id = _create_user(app, 'Admin Banner', 'admin_banner@example.com', is_admin=True)
    _login(client, admin_id)

    # 1. Testar endpoint da API AniList retornando banner e capas
    fake_anilist_media = {
        'id': 105778,
        'title': {'romaji': 'Chainsaw Man', 'english': 'Chainsaw Man', 'native': 'チェンソーマン'},
        'description': 'Denji is a teenage boy living with a Chainsaw Devil.',
        'coverImage': {
            'large': 'https://s4.anilist.co/file/anilistcdn/media/manga/cover/medium/bx105778.jpg',
            'extraLarge': 'https://s4.anilist.co/file/anilistcdn/media/manga/cover/large/bx105778.jpg',
        },
        'bannerImage': 'https://s4.anilist.co/file/anilistcdn/media/manga/banner/105778.jpg',
        'genres': ['Action', 'Supernatural'],
        'status': 'RELEASING',
        'chapters': 150,
        'startDate': {'year': 2018, 'month': 12, 'day': 3},
        'staff': {'edges': []},
    }

    with patch('app.routes.admin_routes.get_manga_by_id', return_value=(fake_anilist_media, None)):
        res_api = client.get('/admin/mangas/api/anilist-details/105778')
        assert res_api.status_code == 200
        json_data = res_api.get_json()
        assert json_data['error'] is None
        manga_payload = json_data['manga']
        assert manga_payload['banner_image'] == 'https://s4.anilist.co/file/anilistcdn/media/manga/banner/105778.jpg'
        assert manga_payload['cover_image_extra_large'] == 'https://s4.anilist.co/file/anilistcdn/media/manga/cover/large/bx105778.jpg'
        assert manga_payload['cover_image_large'] == 'https://s4.anilist.co/file/anilistcdn/media/manga/cover/medium/bx105778.jpg'

    # 2. Cadastrar novo mangá com banner selecionado (oficial)
    res_create = client.post(
        '/admin/mangas/new',
        data={
            'title': 'Chainsaw Man',
            'anilist_id': '105778',
            'cover_image': 'https://s4.anilist.co/file/anilistcdn/media/manga/cover/large/bx105778.jpg',
            'banner_image': 'https://s4.anilist.co/file/anilistcdn/media/manga/banner/105778.jpg',
            'publication_status': 'RELEASING',
            'is_visible': 'y',
            'is_featured': 'y',
        },
        follow_redirects=True,
    )
    assert res_create.status_code == 200

    with app.app_context():
        m = Manga.query.filter_by(anilist_id=105778).first()
        assert m is not None
        assert m.banner_image == 'https://s4.anilist.co/file/anilistcdn/media/manga/banner/105778.jpg'
        assert m.banner_url == 'https://s4.anilist.co/file/anilistcdn/media/manga/banner/105778.jpg'
        assert m.is_cover_banner is False
        m_id = m.id

    # 3. Editar mangá para usar capa como banner (fallback/blur mode)
    res_edit = client.post(
        f'/admin/mangas/{m_id}/edit',
        data={
            'title': 'Chainsaw Man Part 2',
            'anilist_id': '105778',
            'cover_image': 'https://s4.anilist.co/file/anilistcdn/media/manga/cover/large/bx105778.jpg',
            'banner_image': 'https://s4.anilist.co/file/anilistcdn/media/manga/cover/large/bx105778.jpg',
            'publication_status': 'RELEASING',
            'is_visible': 'y',
            'is_featured': 'y',
        },
        follow_redirects=True,
    )
    assert res_edit.status_code == 200

    with app.app_context():
        m_updated = db.session.get(Manga, m_id)
        assert m_updated.title == 'Chainsaw Man Part 2'
        assert m_updated.banner_image == 'https://s4.anilist.co/file/anilistcdn/media/manga/cover/large/bx105778.jpg'
        # Como o banner_image é a própria capa vertical, is_cover_banner deve ser True
        assert m_updated.is_cover_banner is True

    # 4. Verificar se a página inicial carrega e renderiza o item no carrossel
    home_res = client.get('/')
    assert home_res.status_code == 200
    assert 'Chainsaw Man Part 2'.encode() in home_res.data
    # Confirma aplicação da classe cover-fallback-img quando for capa vertical
    assert 'cover-fallback-img'.encode() in home_res.data

