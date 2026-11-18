import gc
from decimal import Decimal
from io import BytesIO
from pathlib import Path
import re
import shutil
import tempfile

from flask import current_app
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.chapter import Chapter
from app.models.manga import Manga
from app.services.storage_service import get_storage_root

_PDF_MAGIC = b'%PDF-'
_PAGE_COUNT_REGEX = re.compile(rb'/Type\s*/Page\b')
_PAGES_COUNT_DICT_REGEX = re.compile(rb'/Count\s+(\d+)')


class PDFUploadError(Exception):
    """Erro seguro para o usuário ao enviar ou validar arquivo PDF."""


def count_pdf_pages(file_stream):
    """
    Calcula a contagem de páginas de um PDF de forma segura sem dependências externas.
    Retorna pelo menos 1 para um PDF válido.
    """
    try:
        current_pos = file_stream.tell()
        file_stream.seek(0)
        content = file_stream.read()
        file_stream.seek(current_pos)

        # 1. Procurar contagem no dicionário /Pages /Count
        counts = _PAGES_COUNT_DICT_REGEX.findall(content)
        if counts:
            parsed_counts = [int(c) for c in counts if c.isdigit()]
            if parsed_counts:
                max_count = max(parsed_counts)
                if max_count > 0:
                    return max_count

        # 2. Alternativa: contar ocorrências de /Type /Page
        matches = _PAGE_COUNT_REGEX.findall(content)
        if matches:
            pages_matches = len(re.findall(rb'/Type\s*/Pages\b', content))
            direct_pages = len(matches) - pages_matches
            if direct_pages > 0:
                return direct_pages

        return 1
    except Exception:
        return 1


def validate_pdf_file(upload):
    """
    Valida extensão, MIME type, assinatura de bytes (%PDF-) e tamanho máximo.
    """
    filename = getattr(upload, 'filename', '') or ''
    suffix = Path(filename).suffix.lower()
    if suffix != '.pdf':
        raise PDFUploadError('O arquivo selecionado deve possuir extensão .pdf.')

    content_type = getattr(upload, 'content_type', '') or ''
    if content_type and 'pdf' not in content_type.lower() and content_type != 'application/octet-stream':
        raise PDFUploadError('O tipo do arquivo não é um documento PDF válido.')

    stream = getattr(upload, 'stream', None)
    if stream is None:
        raise PDFUploadError('O arquivo enviado é inválido.')

    try:
        stream.seek(0, 2)
        file_size = stream.tell()
        stream.seek(0)
    except (AttributeError, OSError, ValueError):
        raw_data = stream.read()
        if not raw_data:
            raise PDFUploadError('O arquivo enviado está vazio.')
        stream = BytesIO(raw_data)
        upload.stream = stream
        file_size = len(raw_data)

    max_size = current_app.config.get('MAX_CONTENT_LENGTH', 100 * 1024 * 1024)
    if file_size > max_size:
        raise PDFUploadError(f'O arquivo excede o limite máximo permitido de {max_size // (1024 * 1024)}MB.')

    header = stream.read(1024)
    stream.seek(0)
    if not header.startswith(_PDF_MAGIC) and _PDF_MAGIC not in header[:64]:
        raise PDFUploadError('O arquivo não é um documento PDF válido (cabeçalho inválido).')

    return file_size


def save_chapter_pdf(
    upload,
    manga_id,
    anilist_id,
    chapter_number,
    chapter_title=None,
    volume_number=None,
    published_at=None,
    status='published',
    is_available=True,
    uploaded_by_id=None,
    authorization_confirmed=False,
):
    """
    Armazena o arquivo PDF de forma segura em storage/manga/<id>/capitulo_<num>/ e cria o registro Chapter.
    """
    if not authorization_confirmed:
        raise PDFUploadError('É necessário confirmar a autorização para disponibilizar o conteúdo.')

    try:
        anilist_id = int(anilist_id)
        chapter_number = Decimal(str(chapter_number))
        volume_number = Decimal(str(volume_number)) if volume_number not in (None, '') else None
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise PDFUploadError('Identificador da obra ou número do capítulo inválido.') from exc

    if not chapter_number.is_finite() or chapter_number < 0:
        raise PDFUploadError('Número do capítulo inválido.')

    # Verificar duplicidade associada à obra
    if manga_id is None:
        manga_record = Manga.query.filter_by(anilist_id=anilist_id).first()
        if manga_record:
            manga_id = manga_record.id

    dup_query = Chapter.query.filter(
        Chapter.chapter_number == chapter_number,
    )
    if manga_id is not None:
        existing = dup_query.filter(
            (Chapter.manga_id == manga_id) | (Chapter.anilist_id == anilist_id)
        ).first()
    else:
        existing = dup_query.filter_by(anilist_id=anilist_id).first()

    if existing:
        raise PDFUploadError(f'O capítulo {chapter_number} já está cadastrado para esta obra.')

    file_size = validate_pdf_file(upload)
    page_count = count_pdf_pages(upload.stream)

    raw_filename = getattr(upload, 'filename', 'chapter.pdf') or 'chapter.pdf'
    safe_name = secure_filename(Path(raw_filename).name) or 'chapter.pdf'
    if not safe_name.lower().endswith('.pdf'):
        safe_name = f'{safe_name}.pdf'

    chapter_label = format(chapter_number.normalize(), 'f').replace('.', '_')
    folder_name = f'capitulo_{chapter_label}'
    relative_dir = Path(str(anilist_id)) / folder_name
    relative_file_path = relative_dir / safe_name

    storage_root = get_storage_root()
    storage_root.mkdir(parents=True, exist_ok=True)

    destination_dir = (storage_root / relative_dir).resolve()
    if not destination_dir.is_relative_to(storage_root):
        raise PDFUploadError('Caminho de armazenamento inseguro detectado.')

    temp_dir = Path(tempfile.mkdtemp(prefix='.pdf-import-', dir=storage_root))
    try:
        temp_file = temp_dir / safe_name
        upload.stream.seek(0)
        with open(temp_file, 'wb') as dst:
            shutil.copyfileobj(upload.stream, dst)

        destination_dir.mkdir(parents=True, exist_ok=True)
        final_file = destination_dir / safe_name
        shutil.move(str(temp_file), str(final_file))

        chapter = Chapter(
            anilist_id=anilist_id,
            manga_id=manga_id,
            chapter_number=chapter_number,
            chapter_title=(chapter_title or '').strip() or None,
            volume_number=volume_number,
            folder_path=relative_file_path.as_posix(),
            original_filename=raw_filename,
            file_size=file_size,
            file_type='pdf',
            page_count=page_count,
            is_available=is_available,
            status=status or 'published',
            published_at=published_at,
            authorization_confirmed=True,
            uploaded_by_id=uploaded_by_id,
        )
        db.session.add(chapter)
        db.session.commit()
        return chapter
    except Exception as exc:
        db.session.rollback()
        if destination_dir.exists():
            shutil.rmtree(destination_dir, ignore_errors=True)
        if isinstance(exc, PDFUploadError):
            raise
        raise PDFUploadError('Não foi possível gravar o arquivo PDF no armazenamento local.') from exc
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def replace_chapter_pdf(chapter, upload):
    """
    Substitui o arquivo PDF de um capítulo com segurança.
    Valida o novo arquivo antes de remover o antigo.
    """
    file_size = validate_pdf_file(upload)
    page_count = count_pdf_pages(upload.stream)

    raw_filename = getattr(upload, 'filename', 'chapter.pdf') or 'chapter.pdf'
    safe_name = secure_filename(Path(raw_filename).name) or 'chapter.pdf'
    if not safe_name.lower().endswith('.pdf'):
        safe_name = f'{safe_name}.pdf'

    storage_root = get_storage_root()
    relative_path = Path(chapter.folder_path)
    old_file_path = (storage_root / relative_path).resolve()

    temp_dir = Path(tempfile.mkdtemp(prefix='.pdf-replace-', dir=storage_root))
    try:
        temp_file = temp_dir / safe_name
        upload.stream.seek(0)
        with open(temp_file, 'wb') as dst:
            shutil.copyfileobj(upload.stream, dst)

        if old_file_path.is_file():
            target_dir = old_file_path.parent
            new_relative = relative_path.parent / safe_name
        else:
            target_dir = old_file_path
            new_relative = relative_path / safe_name

        target_dir.mkdir(parents=True, exist_ok=True)
        new_file_path = (storage_root / new_relative).resolve()

        if old_file_path.is_file() and old_file_path.exists() and old_file_path != new_file_path:
            old_file_path.unlink(missing_ok=True)
        elif old_file_path.is_dir() and old_file_path.exists() and old_file_path != target_dir:
            shutil.rmtree(old_file_path, ignore_errors=True)
            target_dir.mkdir(parents=True, exist_ok=True)

        shutil.move(str(temp_file), str(new_file_path))

        chapter.folder_path = new_relative.as_posix()
        chapter.original_filename = raw_filename
        chapter.file_size = file_size
        chapter.file_type = 'pdf'
        chapter.page_count = page_count
        db.session.commit()
        return chapter
    except Exception as exc:
        db.session.rollback()
        if isinstance(exc, PDFUploadError):
            raise
        raise PDFUploadError('Erro ao substituir o arquivo PDF do capítulo.') from exc
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def delete_chapter_file(chapter):
    """
    Remove os arquivos associados ao capítulo do disco e o registro do banco.
    """
    storage_root = get_storage_root()
    relative_path = Path(chapter.folder_path)
    full_path = (storage_root / relative_path).resolve()

    if full_path.is_relative_to(storage_root):
        if full_path.is_file():
            parent_dir = full_path.parent
            gc.collect()
            try:
                full_path.unlink(missing_ok=True)
            except OSError:
                gc.collect()
                try:
                    full_path.unlink(missing_ok=True)
                except OSError:
                    pass
            try:
                if parent_dir.is_dir() and not any(parent_dir.iterdir()):
                    parent_dir.rmdir()
            except OSError:
                pass
        elif full_path.is_dir():
            gc.collect()
            try:
                shutil.rmtree(full_path, ignore_errors=True)
            except OSError:
                pass

    db.session.delete(chapter)
    db.session.commit()
