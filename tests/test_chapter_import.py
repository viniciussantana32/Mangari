from decimal import Decimal
from io import BytesIO
import zipfile

import pytest

from app.extensions import db
from app.models.chapter import Chapter
from app.services.chapter_import_service import ChapterImportError, import_chapter, natural_sort_key
from werkzeug.datastructures import FileStorage

_JPEG = b'\xff\xd8\xff\xe0mangari-test-image'
_PNG = b'\x89PNG\r\n\x1a\nmangari-test-image'


def archive_file(entries, filename='chapter.cbz'):
    stream = BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for name, content in entries:
            archive.writestr(name, content)
    stream.seek(0)
    return FileStorage(stream=stream, filename=filename)


def test_natural_sort_orders_page_numbers_numerically():
    names = ['11.jpg', '2.jpg', '1.jpg', '10.jpg']
    assert sorted(names, key=natural_sort_key) == ['1.jpg', '2.jpg', '10.jpg', '11.jpg']


def test_import_chapter_extracts_pages_in_natural_order(app, tmp_path):
    with app.app_context():
        app.config['MANGA_STORAGE_DIR'] = str(tmp_path)
        chapter = import_chapter(
            archive_file([('10.jpg', _JPEG + b'10'), ('2.jpg', _JPEG + b'2'), ('1.jpg', _JPEG + b'1')]),
            anilist_id=30002,
            chapter_number=Decimal('1.5'),
            chapter_title='Pilot',
            volume_number=1,
            uploaded_by_id=None,
            authorization_confirmed=True,
        )

        assert chapter.page_count == 3
        assert chapter.chapter_number == Decimal('1.5')
        page_folder = tmp_path / chapter.folder_path
        assert (page_folder / '0001.jpg').read_bytes() == _JPEG + b'1'
        assert (page_folder / '0002.jpg').read_bytes() == _JPEG + b'2'
        assert (page_folder / '0003.jpg').read_bytes() == _JPEG + b'10'


@pytest.mark.parametrize(
    ('entries', 'message'),
    [
        ([('page.exe', b'MZbad')], 'formato não permitido'),
        ([('../outside.jpg', _JPEG)], 'caminho não permitido'),
        ([('page.jpg', _PNG)], 'não corresponde ao formato'),
    ],
)
def test_import_rejects_unsafe_or_mismatched_archive_contents(app, tmp_path, entries, message):
    with app.app_context():
        app.config['MANGA_STORAGE_DIR'] = str(tmp_path)
        with pytest.raises(ChapterImportError, match=message):
            import_chapter(
                archive_file(entries),
                anilist_id=30002,
                chapter_number=1,
                authorization_confirmed=True,
            )
        assert list(tmp_path.iterdir()) == []


def test_import_rejects_invalid_archive_and_missing_authorization(app, tmp_path):
    with app.app_context():
        app.config['MANGA_STORAGE_DIR'] = str(tmp_path)
        invalid = FileStorage(stream=BytesIO(b'not a zip'), filename='chapter.zip')
        with pytest.raises(ChapterImportError, match='não é um ZIP/CBZ'):
            import_chapter(invalid, 30002, 1, authorization_confirmed=True)
        with pytest.raises(ChapterImportError, match='Confirme que possui autorização'):
            import_chapter(archive_file([('1.jpg', _JPEG)]), 30002, 1)


def test_import_rejects_duplicate_chapters_without_overwriting(app, tmp_path):
    with app.app_context():
        app.config['MANGA_STORAGE_DIR'] = str(tmp_path)
        first = import_chapter(
            archive_file([('1.jpg', _JPEG)]),
            30002,
            Decimal('1'),
            authorization_confirmed=True,
        )
        with pytest.raises(ChapterImportError, match='já foi importado'):
            import_chapter(
                archive_file([('1.jpg', _JPEG + b'other')]),
                30002,
                Decimal('1.000'),
                authorization_confirmed=True,
            )
        assert Chapter.query.count() == 1
        assert (tmp_path / first.folder_path / '0001.jpg').read_bytes() == _JPEG


def test_import_enforces_page_count_limit(app, tmp_path):
    with app.app_context():
        app.config['MANGA_STORAGE_DIR'] = str(tmp_path)
        app.config['MANGA_MAX_PAGES'] = 1
        with pytest.raises(ChapterImportError, match='limite de páginas'):
            import_chapter(
                archive_file([('1.jpg', _JPEG), ('2.jpg', _JPEG)]),
                30002,
                1,
                authorization_confirmed=True,
            )


def test_pdf_upload_security_and_validation(app, tmp_path):
    from app.services.pdf_service import save_chapter_pdf, PDFUploadError
    from werkzeug.datastructures import FileStorage

    with app.app_context():
        app.config['MANGA_STORAGE_DIR'] = str(tmp_path)

        # 1. Arquivo não permitido (ex.: .txt ou .exe)
        fake_txt = FileStorage(stream=BytesIO(b'not a pdf content'), filename='malicious.txt')
        with pytest.raises(PDFUploadError, match='extensão .pdf'):
            save_chapter_pdf(
                upload=fake_txt,
                manga_id=None,
                anilist_id=30002,
                chapter_number=1,
                authorization_confirmed=True,
            )

        # 2. Arquivo com extensão .pdf mas assinatura corrompida / não-PDF
        fake_pdf = FileStorage(stream=BytesIO(b'MZ executable disguised as pdf'), filename='fake.pdf')
        with pytest.raises(PDFUploadError, match='cabeçalho inválido'):
            save_chapter_pdf(
                upload=fake_pdf,
                manga_id=None,
                anilist_id=30002,
                chapter_number=1,
                authorization_confirmed=True,
            )

