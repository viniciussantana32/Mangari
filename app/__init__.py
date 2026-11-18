import click
from flask import Flask

from .extensions import csrf, db, login_manager, migrate
from .models.user import User
from .routes.admin_routes import admin_bp
from .routes.auth_routes import auth_bp
from .routes.library_routes import library_bp
from .routes.main_routes import main_bp
from .routes.manga_routes import manga_bp
from .routes.reader_routes import reader_bp
from .routes.user_routes import user_bp


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object('config.Config')

    if test_config:
        app.config.from_mapping(test_config)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Filtros Jinja2 personalizados
    @app.template_filter('clean_number')
    @app.template_filter('format_chapter')
    def format_chapter_filter(value):
        """
        Formata números de capítulos removendo casas decimais desnecessárias:
        2.000 -> 2
        2.500 -> 2.5
        10.0 -> 10
        """
        if value is None or value == '':
            return ''
        try:
            from decimal import Decimal
            d = Decimal(str(value))
            # d.normalize() converte 2.000 em 2 e 2.500 em 2.5
            normalized = d.normalize()
            # Formata como string decimal sem notação científica
            return f'{normalized:f}'
        except Exception:
            return str(value)

    @app.template_filter('translate_status')
    def translate_status_filter(status):
        """
        Traduz status de publicação da AniList para Português.
        RELEASING -> Em lançamento
        FINISHED -> Finalizado
        NOT_YET_RELEASED -> Não lançado
        CANCELLED -> Cancelado
        HIATUS -> Em hiato
        """
        if not status:
            return 'Desconhecido'
        normalized = str(status).strip().upper()
        status_map = {
            'RELEASING': 'Em lançamento',
            'FINISHED': 'Finalizado',
            'NOT_YET_RELEASED': 'Não lançado',
            'CANCELLED': 'Cancelado',
            'HIATUS': 'Em hiato',
        }
        return status_map.get(normalized, str(status).title())

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(library_bp)
    app.register_blueprint(manga_bp)
    app.register_blueprint(reader_bp)
    app.register_blueprint(admin_bp)

    @app.cli.command('make-admin')
    @click.argument('email')
    def make_admin(email):
        """Promove um usuário cadastrado para administrador pelo e-mail."""
        clean_email = email.strip().lower()
        user = User.query.filter_by(email=clean_email).first()
        if not user:
            click.echo(f"Erro: Usuário com e-mail '{clean_email}' não foi encontrado.")
            return
        if user.is_admin:
            click.echo(f"Aviso: O usuário '{user.name}' ({user.email}) já possui privilégios de administrador.")
            return

        user.is_admin = True
        user.is_active = True
        db.session.commit()
        click.echo(f"Sucesso: O usuário '{user.name}' ({user.email}) foi promovido a administrador.")

    with app.app_context():
        db.create_all()

    return app
