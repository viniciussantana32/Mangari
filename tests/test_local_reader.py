from decimal import Decimal
from io import BytesIO
import zipfile

from app.extensions import db
from app.models.chapter import Chapter
from app.models.library_entry import LibraryEntry
from app.models.reading_progress import ReadingProgress
from app.models.user import User
from werkzeug.security import generate_password_hash


def create_user(app, email, is_admin=False):
    with app.app_context():
        user = User(
            name='Reader',
            email=email,
            password_hash=generate_password_hash('secret'),
            is_admin=is_admin,
        )
        db.session.add(user)
        db.session.commit()
        return user.id


def login(client, user_id):
    with client.session_transaction() as session:
        session['_user_id'] = str(user_id)
        session['_fresh'] = True


def make_chapter(app, tmp_path, anilist_id=30002):
    page_folder = tmp_path / str(anilist_id) / 'local-chapter'
    page_folder.mkdir(parents=True)
    (page_folder / '0001.jpg').write_bytes(b'\xff\xd8\xfftest')
    (page_folder / '0002.png').write_bytes(b'\x89PNG\r\n\x1a\ntest')
    with app.app_context():
        chapter = Chapter(
            anilist_id=anilist_id,
            chapter_number=Decimal('1'),
            chapter_title='Chapter one',
            folder_path=f'{anilist_id}/local-chapter',
            page_count=2,
            is_available=True,
            authorization_confirmed=True,
        )
        db.session.add(chapter)
        db.session.commit()
        return chapter.id


def test_page_route_requires_login_and_serves_page_from_private_storage(client, app, tmp_path):
    app.config['MANGA_STORAGE_DIR'] = str(tmp_path)
    chapter_id = make_chapter(app, tmp_path)

    anonymous_response = client.get(f'/reader/chapter/{chapter_id}/page/1')
    assert anonymous_response.status_code == 302

    user_id = create_user(app, 'reader1@example.com')
    login(client, user_id)
    response = client.get(f'/reader/chapter/{chapter_id}/page/1')
    assert response.status_code == 200, response.headers.get('Location')
    assert response.data == b'\xff\xd8\xfftest'

    assert client.get(f'/reader/chapter/{chapter_id}/page/3').status_code == 404


def test_progress_is_private_restorable_and_keeps_completion(client, app, tmp_path):
    app.config['MANGA_STORAGE_DIR'] = str(tmp_path)
    chapter_id = make_chapter(app, tmp_path)
    user_id = create_user(app, 'reader2@example.com')
    other_user_id = create_user(app, 'reader3@example.com')
    login(client, user_id)

    response = client.post(
        f'/reader/chapter/{chapter_id}/progress',
        json={'current_page': 2, 'is_completed': True},
    )
    assert response.status_code == 200
    assert response.json['is_completed'] is True

    response = client.post(
        f'/reader/chapter/{chapter_id}/progress',
        json={'current_page': 1, 'is_completed': False},
    )
    assert response.status_code == 200

    with app.app_context():
        progress = ReadingProgress.query.filter_by(user_id=user_id, chapter_id=chapter_id).one()
        assert progress.current_page == 1
        assert progress.is_completed is True

    login(client, other_user_id)
    response = client.get(f'/reader/chapter/{chapter_id}')
    assert response.status_code == 200
    assert b'data-initial-page="1"' in response.data
    with app.app_context():
        assert ReadingProgress.query.filter_by(user_id=other_user_id, chapter_id=chapter_id).first() is None


def test_reading_updates_library_chapter_without_decreasing_or_completing_entry(client, app, tmp_path):
    app.config['MANGA_STORAGE_DIR'] = str(tmp_path)
    chapter_id = make_chapter(app, tmp_path)
    user_id = create_user(app, 'library-reader@example.com')
    login(client, user_id)
    with app.app_context():
        entry = LibraryEntry(
            user_id=user_id,
            anilist_id=30002,
            manga_title='Authorized test title',
            reading_status='Want to Read',
            current_chapter=0,
        )
        db.session.add(entry)
        db.session.commit()

    response = client.post(
        f'/reader/chapter/{chapter_id}/progress',
        json={'current_page': 1},
    )
    assert response.status_code == 200
    with app.app_context():
        entry = LibraryEntry.query.filter_by(user_id=user_id, anilist_id=30002).one()
        assert entry.current_chapter == 1
        assert entry.reading_status == 'Reading'

        entry.current_chapter = 5
        entry.reading_status = 'Completed'
        db.session.commit()

    response = client.post(
        f'/reader/chapter/{chapter_id}/progress',
        json={'current_page': 2},
    )
    assert response.status_code == 200
    with app.app_context():
        entry = LibraryEntry.query.filter_by(user_id=user_id, anilist_id=30002).one()
        assert entry.current_chapter == 5
        assert entry.reading_status == 'Completed'


def test_admin_routes_are_restricted_to_admin(client, app, tmp_path):
    app.config['MANGA_STORAGE_DIR'] = str(tmp_path)
    user_id = create_user(app, 'regular@example.com')
    login(client, user_id)

    assert client.get('/reader/manage').status_code == 403
    assert client.get('/reader/import').status_code == 403


def test_legacy_import_view_redirects_admin_to_admin_chapters(client, app):
    admin_id = create_user(app, 'admin-redirect@example.com', is_admin=True)
    login(client, admin_id)

    res = client.get('/reader/import')
    assert res.status_code == 302
    assert '/admin/chapters' in res.location

    res_with_param = client.get('/reader/import?manga_id=42')
    assert res_with_param.status_code == 302
    assert '/admin/chapters?manga_id=42' in res_with_param.location



def test_manga_detail_chapter_listing_available_and_unavailable(client, app):
    from unittest.mock import patch
    from app.models.manga import Manga

    fake_anilist_manga = {
        'id': 30656,
        'title': {'romaji': 'Vagabond'},
        'description': 'Miyamoto Musashi journey.',
        'coverImage': {'extraLarge': 'https://example.com/vaga.jpg', 'large': 'https://example.com/vaga.jpg'},
        'bannerImage': None,
        'genres': ['Action', 'Historical'],
        'status': 'RELEASING',
        'chapters': None,
        'averageScore': 90,
    }

    with app.app_context():
        m = Manga(title='Vagabond', anilist_id=30656, anilist_chapters=4)
        db.session.add(m)
        db.session.commit()
        m_id = m.id

        ch2 = Chapter(
            anilist_id=30656,
            manga_id=m_id,
            chapter_number=Decimal('2'),
            chapter_title='O Caminho da Espada',
            folder_path='30656/0002',
            page_count=20,
            is_available=True,
            authorization_confirmed=True,
        )
        db.session.add(ch2)
        db.session.commit()
        ch2_id = ch2.id

    with patch('app.routes.manga_routes.get_manga_by_id', return_value=(fake_anilist_manga, None)):
        res = client.get('/manga/30656')
        assert res.status_code == 200

        # 1. Cabeçalho mostra 1 de 4 capítulos disponíveis
        assert '1 de 4'.encode() in res.data
        assert 'disponíveis'.encode() in res.data

        # 2. Capítulo 2 está disponível com link de leitura
        assert 'Capítulo 2'.encode() in res.data
        assert 'O Caminho da Espada'.encode() in res.data
        assert 'Disponível'.encode() in res.data
        assert f'/reader/chapter/{ch2_id}'.encode() in res.data

        # 3. Capítulos 1, 3 e 4 estão listados como Indisponíveis
        assert 'Capítulo 1'.encode() in res.data
        assert 'Capítulo 3'.encode() in res.data
        assert 'Capítulo 4'.encode() in res.data
        assert 'Indisponível'.encode() in res.data
        assert 'Conteúdo ainda não importado'.encode() in res.data


def test_mangadex_chapter_fallback_integration(client, app):
    from unittest.mock import patch
    from app.models.chapter import Chapter
    from app.models.manga import Manga

    fake_anilist_manga = {
        'id': 30656,
        'title': {'romaji': 'Vagabond'},
        'description': 'Miyamoto Musashi journey.',
        'coverImage': {'extraLarge': 'https://example.com/vaga.jpg', 'large': 'https://example.com/vaga.jpg'},
        'bannerImage': None,
        'genres': ['Action', 'Historical'],
        'status': 'RELEASING',
        'chapters': None,  # AniList não tem total (RELEASING)
        'averageScore': 90,
    }

    with app.app_context():
        # Manga cadastrado sem anilist_chapters definido
        m = Manga(title='Vagabond', anilist_id=30656, anilist_chapters=None)
        db.session.add(m)
        db.session.commit()
        m_id = m.id

        ch1 = Chapter(
            anilist_id=30656,
            manga_id=m_id,
            chapter_number=Decimal('1'),
            chapter_title='Shinmen Takezo',
            folder_path='30656/0001',
            page_count=25,
            is_available=True,
            authorization_confirmed=True,
        )
        db.session.add(ch1)
        db.session.commit()

    with patch('app.routes.manga_routes.get_manga_by_id', return_value=(fake_anilist_manga, None)), \
         patch('app.routes.manga_routes.get_mangadex_chapter_count', return_value=327):
        res = client.get('/manga/30656')
        assert res.status_code == 200

        # Verifica se o fallback do MangaDex (327 capítulos) foi aplicado no cabeçalho e na lista
        assert '1 de 327'.encode() in res.data
        assert 'Capítulo 1'.encode() in res.data
        assert 'Capítulo 327'.encode() in res.data

        # Verifica se persistiu no banco local
        with app.app_context():
            updated_manga = Manga.query.filter_by(anilist_id=30656).first()
            assert updated_manga.anilist_chapters == 327



