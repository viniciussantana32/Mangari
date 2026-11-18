from decimal import Decimal
from io import BytesIO
import zipfile

import pytest

from app.extensions import db
from app.models.chapter import Chapter
from app.models.reading_progress import ReadingProgress
from app.models.user import User
from app.services.chapter_import_service import ChapterImportError, import_chapter
from werkzeug.security import generate_password_hash
from werkzeug.datastructures import FileStorage

_JPEG = b'\xff\xd8\xff\xe0phase-one-test'


def _create_user(app, email, is_admin=False):
    with app.app_context():
        user = User(
            name='Reader admin test',
            email=email,
            password_hash=generate_password_hash('secret'),
            is_admin=is_admin,
        )
        db.session.add(user)
        db.session.commit()
        return user.id


def _login(client, user_id):
    with client.session_transaction() as session:
        session['_user_id'] = str(user_id)
        session['_fresh'] = True


def _chapter(app, storage_dir, anilist_id=43001):
    folder = storage_dir / str(anilist_id) / 'capitulo_1'
    folder.mkdir(parents=True)
    (folder / '0001.jpg').write_bytes(_JPEG)
    with app.app_context():
        chapter = Chapter(
            anilist_id=anilist_id,
            chapter_number=Decimal('1'),
            chapter_title='Pilot',
            folder_path=f'{anilist_id}/capitulo_1',
            page_count=1,
            is_available=True,
            authorization_confirmed=True,
        )
        db.session.add(chapter)
        db.session.commit()
        return chapter.id


def _archive(entries, filename='chapter.cbz'):
    stream = BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for name, contents in entries:
            archive.writestr(name, contents)
    stream.seek(0)
    return FileStorage(stream=stream, filename=filename)


def test_admin_management_metadata_edit_and_media_route(client, app, tmp_path, monkeypatch):
    from app.routes import reader_routes

    app.config['MANGA_STORAGE_DIR'] = str(tmp_path)
    admin_id = _create_user(app, 'phase1-admin@example.com', is_admin=True)
    chapter_id = _chapter(app, tmp_path)
    monkeypatch.setattr(reader_routes, 'get_manga_by_id', lambda manga_id: (
        {
            'title': {'english': 'Test Manga'},
            'coverImage': {'large': 'https://example.test/cover.jpg'},
        },
        None,
    ))
    _login(client, admin_id)

    response = client.get('/reader/manage')
    assert response.status_code == 200
    assert b'Test Manga' in response.data
    assert b'1 cap' in response.data

    response = client.get('/reader/manage/manga/43001')
    assert response.status_code == 200
    assert b'Editar metadados' in response.data

    response = client.post(
        f'/reader/chapter/{chapter_id}/edit',
        data={
            'chapter_title': 'Updated title',
            'volume_number': '2.5',
            'is_available': 'y',
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert 'Metadados do capítulo atualizados.'.encode() in response.data

    with app.app_context():
        chapter = db.session.get(Chapter, chapter_id)
        assert chapter.chapter_title == 'Updated title'
        assert chapter.volume_number == Decimal('2.500')

    response = client.get('/reader/media/43001/{}/1'.format(chapter_id))
    assert response.status_code == 200
    assert response.data == _JPEG
    response.close()
    assert client.get('/reader/media/43002/{}/1'.format(chapter_id)).status_code == 404

    with app.app_context():
        chapter = db.session.get(Chapter, chapter_id)
        db.session.add(ReadingProgress(user_id=admin_id, chapter=chapter, current_page=1))
        db.session.commit()
    response = client.post(f'/reader/chapter/{chapter_id}/delete')
    assert response.status_code == 302
    assert not (tmp_path / '43001' / 'capitulo_1').exists()
    with app.app_context():
        assert db.session.get(Chapter, chapter_id) is None
        assert ReadingProgress.query.filter_by(user_id=admin_id, chapter_id=chapter_id).first() is None


def test_admin_routes_require_admin_and_login(client, app):
    regular_id = _create_user(app, 'phase1-user@example.com')
    assert client.get('/reader/manage').status_code == 302
    _login(client, regular_id)
    assert client.get('/reader/manage').status_code == 403
    assert client.get('/reader/manage/manga/43001').status_code == 403
    assert client.get('/reader/chapter/1/edit').status_code == 403


def test_admin_manga_list_falls_back_when_anilist_is_unavailable(client, app, monkeypatch):
    from app.routes import reader_routes

    admin_id = _create_user(app, 'phase1-fallback@example.com', is_admin=True)
    with app.app_context():
        chapter = Chapter(
            anilist_id=43002,
            chapter_number=Decimal('1'),
            folder_path='43002/capitulo_1',
            page_count=1,
            is_available=True,
        )
        db.session.add(chapter)
        db.session.commit()
        monkeypatch.setattr(reader_routes, 'get_manga_by_id', lambda manga_id: (None, 'offline'))
        with client.session_transaction() as session:
            session['_user_id'] = str(admin_id)
            session['_fresh'] = True

    response = client.get('/reader/manage')
    assert response.status_code == 200
    assert b'AniList 43002' in response.data
    assert b'Metadados temporariamente indispon' in response.data


def test_import_ignores_common_system_files_and_uses_chapter_folder(app, tmp_path):
    with app.app_context():
        app.config['MANGA_STORAGE_DIR'] = str(tmp_path)
        chapter = import_chapter(
            _archive([
                ('10.jpg', _JPEG + b'10'),
                ('__MACOSX/._1.jpg', b'not an image'),
                ('.hidden.jpg', b'not an image'),
                ('Thumbs.db', b'not an image'),
                ('2.jpg', _JPEG + b'2'),
            ]),
            anilist_id=43003,
            chapter_number=Decimal('1.5'),
            authorization_confirmed=True,
        )

        assert chapter.folder_path == '43003/capitulo_1_5'
        assert chapter.page_count == 2
        page_folder = tmp_path / chapter.folder_path
        assert (page_folder / '0001.jpg').read_bytes() == _JPEG + b'2'
        assert (page_folder / '0002.jpg').read_bytes() == _JPEG + b'10'


def test_import_rejects_windows_absolute_paths_and_uncompressed_size_limit(app, tmp_path):
    with app.app_context():
        app.config['MANGA_STORAGE_DIR'] = str(tmp_path)
        with pytest.raises(ChapterImportError, match='caminho não permitido'):
            import_chapter(
                _archive([(r'C:\outside\1.jpg', _JPEG)]),
                anilist_id=43004,
                chapter_number=1,
                authorization_confirmed=True,
            )

        app.config['MANGA_MAX_EXTRACTED_SIZE'] = 8
        with pytest.raises(ChapterImportError, match='tamanho descompactado'):
            import_chapter(
                _archive([('1.jpg', _JPEG)]),
                anilist_id=43004,
                chapter_number=1,
                authorization_confirmed=True,
            )
        assert list(tmp_path.iterdir()) == []


def test_import_rejects_archives_without_pages_and_enforces_archive_size(app, tmp_path):
    with app.app_context():
        app.config['MANGA_STORAGE_DIR'] = str(tmp_path)
        with pytest.raises(ChapterImportError, match='Selecione um arquivo'):
            import_chapter(
                _archive([('1.jpg', _JPEG)], filename='chapter.txt'),
                anilist_id=43005,
                chapter_number=1,
                authorization_confirmed=True,
            )
        with pytest.raises(ChapterImportError, match='não contém páginas'):
            import_chapter(
                _archive([('__MACOSX/._page.jpg', b'not a page')]),
                anilist_id=43005,
                chapter_number=1,
                authorization_confirmed=True,
            )

        app.config['MANGA_MAX_ARCHIVE_SIZE'] = 16
        with pytest.raises(ChapterImportError, match='tamanho máximo'):
            import_chapter(
                _archive([('1.jpg', _JPEG)]),
                anilist_id=43005,
                chapter_number=1,
                authorization_confirmed=True,
            )
        assert list(tmp_path.iterdir()) == []


def test_import_does_not_remove_existing_destination_on_collision(app, tmp_path):
    with app.app_context():
        app.config['MANGA_STORAGE_DIR'] = str(tmp_path)
        existing_folder = tmp_path / '43006' / 'capitulo_1'
        existing_folder.mkdir(parents=True)
        marker = existing_folder / 'keep.txt'
        marker.write_text('existing data', encoding='utf-8')

        with pytest.raises(ChapterImportError, match='já foi importado'):
            import_chapter(
                _archive([('1.jpg', _JPEG)]),
                anilist_id=43006,
                chapter_number=1,
                authorization_confirmed=True,
            )

        assert marker.read_text(encoding='utf-8') == 'existing data'
        assert len(list(tmp_path.glob('.import-*'))) == 0


def test_storage_configuration_cannot_point_inside_public_static(app, tmp_path):
    from app.services.storage_service import get_storage_root

    with app.app_context():
        app.config['STORAGE_DIR'] = app.static_folder
        with pytest.raises(ValueError, match='fora da pasta pública static'):
            get_storage_root()
