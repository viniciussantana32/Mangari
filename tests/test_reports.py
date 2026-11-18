from datetime import datetime, timezone
from app.extensions import db
from app.models.admin_log import AdminLog
from app.models.manga import Manga
from app.models.user import User


def _create_user(app, name, email, is_admin=False, is_active=True):
    from werkzeug.security import generate_password_hash

    with app.app_context():
        user = User(
            name=name,
            email=email,
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


def test_reports_access_control(client, app):
    user_id = _create_user(app, 'Normal User', 'normal@example.com', is_admin=False)
    admin_id = _create_user(app, 'Admin User', 'admin_rep@example.com', is_admin=True)

    # 1. Anônimo deve ser redirecionado para o login
    res_anon = client.get('/admin/reports')
    assert res_anon.status_code == 302
    assert '/auth/login' in res_anon.headers['Location']

    # 2. Usuário comum deve receber 403 Forbidden
    _login(client, user_id)
    res_user = client.get('/admin/reports')
    assert res_user.status_code == 403

    # 3. Administrador deve acessar normalmente (200 OK)
    _login(client, admin_id)
    res_admin = client.get('/admin/reports')
    assert res_admin.status_code == 200
    assert 'Central de Relatórios Administrativos'.encode() in res_admin.data


def test_users_report_filtering_and_preview(client, app):
    admin_id = _create_user(app, 'Chief Admin', 'chief@example.com', is_admin=True, is_active=True)
    _create_user(app, 'Regular Active', 'active@example.com', is_admin=False, is_active=True)
    _create_user(app, 'Blocked Guy', 'blocked@example.com', is_admin=False, is_active=False)

    _login(client, admin_id)

    # 1. Visualizar todos os usuários
    res_all = client.get('/admin/reports?tab=users')
    assert res_all.status_code == 200
    assert 'chief@example.com'.encode() in res_all.data
    assert 'active@example.com'.encode() in res_all.data
    assert 'blocked@example.com'.encode() in res_all.data

    # 2. Filtrar apenas administradores
    res_admins = client.get('/admin/reports?tab=users&role=admin')
    assert res_admins.status_code == 200
    assert 'chief@example.com'.encode() in res_admins.data
    assert 'active@example.com'.encode() not in res_admins.data

    # 3. Filtrar apenas bloqueados
    res_blocked = client.get('/admin/reports?tab=users&status=blocked')
    assert res_blocked.status_code == 200
    assert 'blocked@example.com'.encode() in res_blocked.data
    assert 'active@example.com'.encode() not in res_blocked.data


def test_mangas_report_filtering_and_preview(client, app):
    admin_id = _create_user(app, 'Manga Admin', 'm_admin@example.com', is_admin=True)

    with app.app_context():
        m1 = Manga(
            title='Manga Visivel Em Publicacao',
            author='Autor A',
            publication_status='RELEASING',
            is_visible=True,
            is_featured=True,
        )
        m2 = Manga(
            title='Manga Oculto Finalizado',
            author='Autor B',
            publication_status='FINISHED',
            is_visible=False,
            is_featured=False,
        )
        db.session.add_all([m1, m2])
        db.session.commit()

    _login(client, admin_id)

    # 1. Visualizar aba de mangás
    res = client.get('/admin/reports?tab=mangas')
    assert res.status_code == 200
    assert 'Manga Visivel Em Publicacao'.encode() in res.data
    assert 'Manga Oculto Finalizado'.encode() in res.data

    # 2. Filtrar por status FINISHED
    res_fin = client.get('/admin/reports?tab=mangas&publication_status=FINISHED')
    assert res_fin.status_code == 200
    assert 'Manga Oculto Finalizado'.encode() in res_fin.data
    assert 'Manga Visivel Em Publicacao'.encode() not in res_fin.data

    # 3. Filtrar por destaque na home
    res_feat = client.get('/admin/reports?tab=mangas&is_featured=yes')
    assert res_feat.status_code == 200
    assert 'Manga Visivel Em Publicacao'.encode() in res_feat.data
    assert 'Manga Oculto Finalizado'.encode() not in res_feat.data


def test_reports_csv_export_and_security(client, app):
    admin_id = _create_user(app, 'Secret Admin', 'secret@example.com', is_admin=True)
    _create_user(app, 'John Doe', 'john@example.com', is_admin=False)

    _login(client, admin_id)

    # 1. Exportar CSV de Usuários
    res_csv = client.get('/admin/reports/export/csv?type=users')
    assert res_csv.status_code == 200
    assert res_csv.mimetype == 'text/csv'
    assert 'attachment;' in res_csv.headers['Content-Disposition']

    content_str = res_csv.data.decode('utf-8')
    # Validar que contém cabeçalho e dados
    assert 'ID;Nome;E-mail;Papel;Status;Data de Cadastro' in content_str
    assert 'secret@example.com' in content_str
    assert 'john@example.com' in content_str

    # Segurança: NUNCA deve expor senhas ou hashes
    assert 'password_hash' not in content_str
    assert 'password123' not in content_str
    assert 'pbkdf2' not in content_str

    # 2. Exportar CSV de Mangás
    res_manga_csv = client.get('/admin/reports/export/csv?type=mangas')
    assert res_manga_csv.status_code == 200
    assert res_manga_csv.mimetype == 'text/csv'
    manga_csv_str = res_manga_csv.data.decode('utf-8')
    assert 'ID;Título;Autor;Status de Publicação' in manga_csv_str

    # 3. Validar se a exportação foi registrada no AdminLog
    with app.app_context():
        log = AdminLog.query.filter_by(action='report_exported_csv').first()
        assert log is not None
        assert 'Exportou relatório' in log.description


def test_reports_pdf_export(client, app):
    admin_id = _create_user(app, 'PDF Admin', 'pdf_admin@example.com', is_admin=True)
    _create_user(app, 'Alice', 'alice@example.com', is_admin=False)

    with app.app_context():
        m = Manga(
            title='Berserk Report Test',
            author='Kentaro Miura',
            publication_status='FINISHED',
            is_visible=True,
            is_featured=True,
        )
        db.session.add(m)
        db.session.commit()

    _login(client, admin_id)

    # 1. Exportar PDF de Usuários
    res_pdf_users = client.get('/admin/reports/export/pdf?type=users')
    assert res_pdf_users.status_code == 200
    assert res_pdf_users.mimetype == 'application/pdf'
    assert res_pdf_users.data.startswith(b'%PDF-')

    # 2. Exportar PDF de Mangás
    res_pdf_mangas = client.get('/admin/reports/export/pdf?type=mangas')
    assert res_pdf_mangas.status_code == 200
    assert res_pdf_mangas.mimetype == 'application/pdf'
    assert res_pdf_mangas.data.startswith(b'%PDF-')

    # 3. Validar registro de log para PDF
    with app.app_context():
        log_pdf = AdminLog.query.filter_by(action='report_exported_pdf').first()
        assert log_pdf is not None
        assert 'Exportou relatório' in log_pdf.description
