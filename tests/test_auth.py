def test_registration_and_login(client):
    response = client.post('/auth/register', data={
        'name': 'Alice',
        'email': 'alice@example.com',
        'password': 'secret123',
        'confirm_password': 'secret123',
    }, follow_redirects=True)
    assert response.status_code == 200

    login_response = client.post('/auth/login', data={
        'email': 'alice@example.com',
        'password': 'secret123',
    }, follow_redirects=True)
    assert login_response.status_code == 200
    assert b'Logged in successfully' in login_response.data


def test_login_error(client):
    response = client.post('/auth/login', data={
        'email': 'no-user@example.com',
        'password': 'wrong',
    }, follow_redirects=True)
    assert b'E-mail ou senha' in response.data or b'Invalid email or password' in response.data


def test_login_brute_force_lockout(client):
    # Envia 5 tentativas inválidas consecutivas
    for _ in range(5):
        resp = client.post('/auth/login', data={
            'email': 'victim@example.com',
            'password': 'wrong-password',
        }, follow_redirects=True)

    # A 5ª tentativa bloqueia o acesso
    assert ('Limite de 5 tentativas inválidas atingido'.encode('utf-8') in resp.data
            or 'temporariamente suspenso'.encode('utf-8') in resp.data)

    # A 6ª tentativa deve ser impedida antes mesmo de validar
    locked_resp = client.post('/auth/login', data={
        'email': 'victim@example.com',
        'password': 'wrong-password',
    }, follow_redirects=True)
    assert 'Muitas tentativas incorretas consecutivas'.encode('utf-8') in locked_resp.data



def test_homepage_shows_live_api_results_and_cover_fallback(client, monkeypatch):
    from app.routes import main_routes

    popular = [{
        'id': 42,
        'title': {'romaji': 'Real title', 'english': None, 'native': None},
        'coverImage': {'large': 'https://cdn.example/cover.jpg', 'extraLarge': None},
        'averageScore': 87,
        'genres': ['Drama'],
        'status': 'RELEASING',
        'startDate': {'year': 2026, 'month': 1, 'day': 2},
    }]
    recent = [{
        **popular[0],
        'id': 84,
        'title': {'romaji': 'Recent title', 'english': None, 'native': None},
        'coverImage': None,
    }]
    monkeypatch.setattr(main_routes, 'get_popular_manga', lambda **kwargs: (popular, None))
    monkeypatch.setattr(main_routes, 'get_recent_manga', lambda **kwargs: (recent, None))

    response = client.get('/')

    assert response.status_code == 200
    assert b'https://cdn.example/cover.jpg' in response.data
    assert b'Real title' in response.data
    assert b'Recent title' in response.data
    assert b'Cover unavailable' in response.data
