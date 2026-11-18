from pathlib import Path

from flask import current_app


def get_storage_root():
    configured = Path(current_app.config['STORAGE_DIR'])
    legacy = Path(current_app.config.get('MANGA_STORAGE_DIR', configured))
    default = Path(current_app.config.get('DEFAULT_STORAGE_DIR', configured))
    if configured == default and legacy != default:
        configured = legacy
    storage_root = configured.resolve()
    static_root = Path(current_app.static_folder).resolve()
    if storage_root == static_root or storage_root.is_relative_to(static_root):
        raise ValueError('STORAGE_DIR deve ficar fora da pasta pública static.')
    return storage_root
