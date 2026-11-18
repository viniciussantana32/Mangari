import os
from pathlib import Path
from dotenv import load_dotenv

base_dir = Path(__file__).resolve().parent.parent

# Carrega as variáveis do arquivo .env se ele existir
load_dotenv(base_dir / '.env')


def _get_env_value(name, default):
    value = os.getenv(name)
    return default if value is None or value == '' else value


class Config:
    SECRET_KEY = _get_env_value('SECRET_KEY', 'change-this-secret-key')
    SQLALCHEMY_DATABASE_URI = _get_env_value(
        'DATABASE_URL',
        'sqlite:///' + str(base_dir / 'mangari_dev.db'),
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 280,
    }
    ANILIST_API_URL = _get_env_value('ANILIST_API_URL', 'https://graphql.anilist.co')
    DEFAULT_STORAGE_DIR = base_dir / 'storage' / 'manga'
    storage_dir_env = _get_env_value('STORAGE_DIR', _get_env_value('MANGA_STORAGE_DIR', str(DEFAULT_STORAGE_DIR)))
    STORAGE_DIR = Path(storage_dir_env)
    if not STORAGE_DIR.is_absolute():
        STORAGE_DIR = base_dir / STORAGE_DIR
    MANGA_STORAGE_DIR = STORAGE_DIR
    MAX_CONTENT_LENGTH = int(_get_env_value('MAX_UPLOAD_SIZE', str(100 * 1024 * 1024)))
    MANGA_MAX_ARCHIVE_SIZE = int(_get_env_value('MANGA_MAX_ARCHIVE_SIZE', str(90 * 1024 * 1024)))
    MANGA_MAX_EXTRACTED_SIZE = int(_get_env_value('MANGA_MAX_EXTRACTED_SIZE', str(500 * 1024 * 1024)))
    MANGA_MAX_PAGES = int(_get_env_value('MANGA_MAX_IMAGES', _get_env_value('MANGA_MAX_PAGES', '1000')))


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
