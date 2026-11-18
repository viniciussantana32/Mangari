from .admin_routes import admin_bp
from .auth_routes import auth_bp
from .library_routes import library_bp
from .main_routes import main_bp
from .manga_routes import manga_bp
from .reader_routes import reader_bp
from .user_routes import user_bp

__all__ = ['admin_bp', 'auth_bp', 'library_bp', 'main_bp', 'manga_bp', 'reader_bp', 'user_bp']
