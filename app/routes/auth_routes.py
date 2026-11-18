import time
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.forms.auth_forms import LoginForm, RegisterForm
from app.models.user import User

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 120  # 2 minutos


def _get_client_ip():
    """Retorna o IP do cliente considerando proxies confiáveis ou conexão direta."""
    return request.headers.get('X-Forwarded-For', request.remote_addr or '127.0.0.1').split(',')[0].strip()


def _is_rate_limited():
    """Verifica se a sessão/IP está bloqueada por excesso de tentativas falhas."""
    now = time.time()
    lockout_until = session.get('login_lockout_until', 0)
    if now < lockout_until:
        remaining = int(lockout_until - now)
        return True, remaining
    return False, 0


def _record_failed_attempt():
    """Registra uma tentativa falha e bloqueia temporariamente se atingir o limite."""
    attempts = session.get('login_failed_attempts', 0) + 1
    session['login_failed_attempts'] = attempts
    if attempts >= MAX_FAILED_ATTEMPTS:
        session['login_lockout_until'] = time.time() + LOCKOUT_DURATION_SECONDS
        return True
    return False


def _clear_login_attempts():
    """Limpa as tentativas de login na sessão após autenticação bem-sucedida."""
    session.pop('login_failed_attempts', None)
    session.pop('login_lockout_until', None)


auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        user = User(
            name=form.name.data.strip(),
            email=form.email.data.strip().lower(),
            password_hash=generate_password_hash(form.password.data),
            is_admin=False,
            is_active=True,
        )
        if User.query.count() == 0:
            user.is_admin = True
        db.session.add(user)
        db.session.commit()
        flash('Your account has been created successfully.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/register.html', form=form)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()

    # Verifica se o usuário está temporariamente bloqueado por força bruta
    is_blocked, remaining = _is_rate_limited()
    if is_blocked:
        flash(
            f'Muitas tentativas incorretas consecutivas. Por segurança, tente novamente em {remaining} segundo(s).',
            'danger',
        )
        return render_template('auth/login.html', form=form)

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.strip().lower()).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            if not user.is_active:
                flash('Sua conta está desativada ou bloqueada. Entre em contato com um administrador.', 'danger')
                return render_template('auth/login.html', form=form)

            _clear_login_attempts()
            login_user(user, remember=form.remember.data)
            flash('Logged in successfully.', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.index'))

        # Registra falha de login
        is_now_blocked = _record_failed_attempt()
        if is_now_blocked:
            flash(
                f'Limite de {MAX_FAILED_ATTEMPTS} tentativas inválidas atingido. Acesso temporariamente suspenso por 2 minutos.',
                'danger',
            )
        else:
            remaining_tries = MAX_FAILED_ATTEMPTS - session.get('login_failed_attempts', 0)
            flash(f'E-mail ou senha inválidos. Restam {remaining_tries} tentativa(s).', 'danger')

    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('main.index'))
