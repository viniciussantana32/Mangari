from app.extensions import db
from app.models.user import User


def test_admin_user_list(client):
    client.post('/auth/register', data={
        'name': 'Admin',
        'email': 'admin@example.com',
        'password': 'secret123',
        'confirm_password': 'secret123',
    })
    with client.session_transaction() as sess:
        sess['_user_id'] = '1'
        sess['_fresh'] = True
    response = client.get('/users')
    assert response.status_code == 200
    assert b'Admin' in response.data


def test_rbac_access_restrictions(client, app):
    # 1. Usuário não autenticado tentando acessar áreas administrativas -> redireciona para login (302)
    res_unauth = client.get('/admin')
    assert res_unauth.status_code == 302
    assert '/auth/login' in res_unauth.location

    res_unauth_reader = client.get('/reader/import')
    assert res_unauth_reader.status_code == 302
    assert '/auth/login' in res_unauth_reader.location

    # 2. Criar e autenticar como usuário comum (role='user', is_admin=False)
    with app.app_context():
        # Usuário 1 criado como admin pelo register
        u_admin = User(name='Admin Boss', email='boss@example.com', password_hash='hash', is_admin=True, is_active=True)
        u_common = User(name='Common User', email='common@example.com', password_hash='hash', is_admin=False, is_active=True)
        db.session.add_all([u_admin, u_common])
        db.session.commit()
        common_id = u_common.id
        admin_id = u_admin.id

    with client.session_transaction() as sess:
        sess['_user_id'] = str(common_id)
        sess['_fresh'] = True

    # Usuário comum tentando acessar /admin ou /reader/import -> HTTP 403 Forbidden
    res_common_admin = client.get('/admin')
    assert res_common_admin.status_code == 403

    res_common_reader = client.get('/reader/import')
    assert res_common_reader.status_code == 403

    # 3. Administrador autenticado -> acessa normalmente
    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)
        sess['_fresh'] = True

    res_admin_panel = client.get('/admin')
    assert res_admin_panel.status_code == 200

    res_admin_reader = client.get('/reader/import')
    assert res_admin_reader.status_code == 302  # Redireciona com segurança para /admin/chapters


def test_last_active_admin_cannot_be_deleted_or_demoted(client, app):
    with app.app_context():
        admin = User(name='Sole Admin', email='sole@example.com', password_hash='hash', is_admin=True, is_active=True)
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id

    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)
        sess['_fresh'] = True

    # 1. Tentar rebaixar o único admin ativo para 'user'
    res_demote = client.post(f'/admin/users/{admin_id}/edit', data={
        'name': 'Sole Admin',
        'email': 'sole@example.com',
        'role': 'user',
        'is_active': 'y',
    }, follow_redirects=True)

    # Bloqueado com aviso
    assert ('você não pode remover sua própria permissão'.encode('utf-8') in res_demote.data
            or 'único administrador ativo'.encode('utf-8') in res_demote.data)

    with app.app_context():
        u = db.session.get(User, admin_id)
        assert u.is_admin is True

    # 2. Tentar excluir o único admin ativo
    res_del = client.post(f'/admin/users/{admin_id}/delete', follow_redirects=True)
    assert ('Você não pode excluir sua própria conta'.encode('utf-8') in res_del.data
            or 'único administrador ativo'.encode('utf-8') in res_del.data)

    with app.app_context():
        u = db.session.get(User, admin_id)
        assert u is not None

