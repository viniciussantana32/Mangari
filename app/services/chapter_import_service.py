import re
import shutil
import tempfile
import uuid
import zipfile
import zlib
from decimal import Decimal
from io import BytesIO
from pathlib import Path, PurePosixPath, PureWindowsPath

from flask import current_app
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db
from app.models.chapter import Chapter
from app.models.manga import Manga
from app.services.storage_service import get_storage_root

_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
_IMAGE_SIGNATURES = {
    '.jpg': lambda data: data.startswith(b'\xff\xd8\xff'),
    '.jpeg': lambda data: data.startswith(b'\xff\xd8\xff'),
    '.png': lambda data: data.startswith(b'\x89PNG\r\n\x1a\n'),
    '.webp': lambda data: data.startswith(b'RIFF') and data[8:12] == b'WEBP',
    '.gif': lambda data: data.startswith((b'GIF87a', b'GIF89a')),
}
_NATURAL_PARTS = re.compile(r'(\d+)')


class ChapterImportError(Exception):
    """A safe, user-facing error while importing an authorized chapter archive."""


def natural_sort_key(value):
    return [
        int(part) if part.isdigit() else part.casefold()
        for part in _NATURAL_PARTS.split(value)
    ]


def _validate_archive(upload):
    max_archive_size = current_app.config['MANGA_MAX_ARCHIVE_SIZE']
    max_extracted_size = current_app.config['MANGA_MAX_EXTRACTED_SIZE']
    max_pages = current_app.config['MANGA_MAX_PAGES']

    filename = getattr(upload, 'filename', '') or ''
    if Path(filename).suffix.lower() not in {'.zip', '.cbz'}:
        raise ChapterImportError('Selecione um arquivo .zip ou .cbz.')

    stream = getattr(upload, 'stream', None)
    if stream is None:
        raise ChapterImportError('O arquivo enviado não é válido.')
    try:
        stream.seek(0, 2)
        archive_size = stream.tell()
        stream.seek(0)
    except (AttributeError, OSError, ValueError):
        raw_data = stream.read()
        if not raw_data:
            raise ChapterImportError('O arquivo enviado está vazio.')
        stream = BytesIO(raw_data)
        if hasattr(upload, 'stream'):
            upload.stream = stream
        archive_size = len(raw_data)
    if archive_size > max_archive_size:
        raise ChapterImportError('O arquivo excede o tamanho máximo permitido.')
    if not zipfile.is_zipfile(stream):
        raise ChapterImportError('O arquivo enviado não é um ZIP/CBZ válido.')
    stream.seek(0)

    try:
        archive = zipfile.ZipFile(upload.stream)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ChapterImportError('Não foi possível abrir o arquivo ZIP/CBZ.') from exc

    try:
        image_entries = []
        total_size = 0
        for info in archive.infolist():
            normalized_name = info.filename.replace('\\', '/')
            path = PurePosixPath(normalized_name)
            windows_path = PureWindowsPath(info.filename)
            mode = info.external_attr >> 16
            if (
                path.is_absolute()
                or windows_path.is_absolute()
                or windows_path.drive
                or '..' in path.parts
                or info.filename.startswith(('\\', '/'))
            ):
                raise ChapterImportError('O arquivo contém um caminho não permitido.')
            if (mode & 0o170000) == 0o120000:
                raise ChapterImportError('Links simbólicos não são permitidos no arquivo.')
            if info.is_dir():
                continue
            if (
                '__macosx' in (part.casefold() for part in path.parts)
                or any(part.startswith('.') for part in path.parts)
                or path.name.casefold() == 'thumbs.db'
            ):
                continue
            if info.flag_bits & 0x1:
                raise ChapterImportError('Arquivos ZIP protegidos por senha não são aceitos.')
            suffix = Path(path.name).suffix.lower()
            if suffix not in _IMAGE_EXTENSIONS:
                raise ChapterImportError('O arquivo contém formato não permitido; use apenas imagens JPG, PNG ou WEBP.')
            if info.file_size <= 0:
                raise ChapterImportError('O arquivo contém uma imagem vazia.')
            total_size += info.file_size
            image_entries.append(info)
            if len(image_entries) > max_pages:
                raise ChapterImportError('O capítulo excede o limite de páginas permitido.')
            if total_size > max_extracted_size:
                raise ChapterImportError('O tamanho descompactado excede o limite permitido.')

        if not image_entries:
            raise ChapterImportError('O arquivo não contém páginas de imagem válidas.')

        image_entries.sort(key=lambda entry: natural_sort_key(entry.filename))
        return image_entries
    except (OSError, zipfile.BadZipFile) as exc:
        raise ChapterImportError('O arquivo ZIP/CBZ está corrompido.') from exc
    finally:
        archive.close()


def import_chapter(
    upload,
    anilist_id,
    chapter_number,
    chapter_title=None,
    volume_number=None,
    uploaded_by_id=None,
    authorization_confirmed=False,
    manga_id=None,
):
    try:
        anilist_id = int(anilist_id)
        chapter_number = Decimal(str(chapter_number))
        volume_number = Decimal(str(volume_number)) if volume_number not in (None, '') else None
        manga_id = int(manga_id) if manga_id is not None else None
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise ChapterImportError('O ID da obra ou o número do capítulo é inválido.') from exc
    if not chapter_number.is_finite() or (volume_number is not None and not volume_number.is_finite()):
        raise ChapterImportError('Os números informados são inválidos.')
    if (
        not 1 <= anilist_id <= 999999999
        or chapter_number < 0
        or chapter_number > Decimal('9999999.999')
        or (volume_number is not None and not Decimal('0') <= volume_number <= Decimal('9999999.999'))
    ):
        raise ChapterImportError('Os números da obra, capítulo e volume devem ser válidos.')
    if not authorization_confirmed:
        raise ChapterImportError('Confirme que possui autorização para disponibilizar este conteúdo.')

    # Validação segura de duplicidade vinculada à obra específica
    if manga_id is None:
        manga_record = Manga.query.filter_by(anilist_id=anilist_id).first()
        if manga_record:
            manga_id = manga_record.id

    duplicate_query = Chapter.query.filter(
        Chapter.chapter_number == chapter_number,
    )
    if manga_id is not None:
        duplicate = duplicate_query.filter(
            (Chapter.manga_id == manga_id) | (Chapter.anilist_id == anilist_id)
        ).first()
    else:
        duplicate = duplicate_query.filter_by(anilist_id=anilist_id).first()

    if duplicate:
        raise ChapterImportError('Este capítulo já foi importado para a obra.')

    entries = _validate_archive(upload)
    chapter_label = format(chapter_number.normalize(), 'f')
    chapter_folder = f'capitulo_{chapter_label.replace(".", "_")}'
    try:
        storage_root = get_storage_root()
        storage_root.mkdir(parents=True, exist_ok=True)
        temporary_root = Path(tempfile.mkdtemp(prefix='.import-', dir=storage_root))
        staging_dir = temporary_root / chapter_folder
        staging_dir.mkdir()
    except (OSError, ValueError) as exc:
        if 'temporary_root' in locals() and temporary_root.exists():
            shutil.rmtree(temporary_root)
        raise ChapterImportError('Não foi possível preparar a pasta de armazenamento do capítulo.') from exc
    destination_relative = Path(str(anilist_id)) / chapter_folder
    destination = (storage_root / destination_relative).resolve()
    if not destination.is_relative_to(storage_root):
        shutil.rmtree(temporary_root)
        raise ChapterImportError('O caminho de armazenamento não é válido.')

    destination_created = False
    try:
        upload.stream.seek(0)
        with zipfile.ZipFile(upload.stream) as archive:
            total_written = 0
            for page_number, entry in enumerate(entries, start=1):
                try:
                    signature = bytearray()
                    written = 0
                    suffix = Path(entry.filename).suffix.lower()
                    normalized_suffix = '.jpg' if suffix == '.jpeg' else suffix
                    page_path = staging_dir / f'{page_number:04d}{normalized_suffix}'
                    with archive.open(entry) as source, page_path.open('wb') as target:
                        while chunk := source.read(64 * 1024):
                            written += len(chunk)
                            total_written += len(chunk)
                            if (
                                written > entry.file_size
                                or total_written > current_app.config['MANGA_MAX_EXTRACTED_SIZE']
                            ):
                                raise ChapterImportError('O conteúdo descompactado excede o limite permitido.')
                            if len(signature) < 12:
                                signature.extend(chunk[:12 - len(signature)])
                            target.write(chunk)
                except (OSError, RuntimeError, EOFError, zipfile.BadZipFile, zlib.error) as exc:
                    raise ChapterImportError('O arquivo está corrompido ou não pôde ser extraído.') from exc
                if written != entry.file_size:
                    raise ChapterImportError('O conteúdo descompactado não corresponde ao tamanho informado.')
                if not _IMAGE_SIGNATURES[suffix](bytes(signature)):
                    page_path.unlink(missing_ok=True)
                    raise ChapterImportError('Uma página não corresponde ao formato de imagem declarado.')

        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise ChapterImportError('Este capítulo já foi importado para a obra.')
        staging_dir.replace(destination)
        destination_created = True

        if manga_id is None:
            manga_record = Manga.query.filter_by(anilist_id=anilist_id).first()
            if manga_record:
                manga_id = manga_record.id

        chapter = Chapter(
            anilist_id=anilist_id,
            manga_id=manga_id,
            chapter_number=chapter_number,
            chapter_title=(chapter_title or '').strip() or None,
            volume_number=volume_number,
            folder_path=destination_relative.as_posix(),
            page_count=len(entries),
            is_available=True,
            authorization_confirmed=True,
            uploaded_by_id=uploaded_by_id,
        )
        db.session.add(chapter)
        db.session.commit()
        return chapter
    except IntegrityError as exc:
        db.session.rollback()
        if destination_created and destination.exists():
            shutil.rmtree(destination)
        raise ChapterImportError('Este capítulo já existe para a obra.') from exc
    except ChapterImportError:
        db.session.rollback()
        if destination_created and destination.exists():
            shutil.rmtree(destination)
        raise
    except (OSError, SQLAlchemyError) as exc:
        db.session.rollback()
        if destination_created and destination.exists():
            shutil.rmtree(destination)
        raise ChapterImportError('Não foi possível armazenar o capítulo. Verifique o espaço e as permissões.') from exc
    finally:
        if temporary_root.exists():
            shutil.rmtree(temporary_root)
