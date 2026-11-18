from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.forms.auth_forms import RegisterForm
from app.models.user import User

user_bp = Blueprint('user', __name__, url_prefix='/users')


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Administrative access required.', 'danger')
            return redirect(url_for('main.index'))
        return view(*args, **kwargs)

    return wrapped_view


@user_bp.route('', methods=['GET'])
@login_required
@admin_required
def list_users():
    search = request.args.get('q', '').strip()
    query = User.query
    if search:
        query = query.filter(or_(User.name.ilike(f'%{search}%'), User.email.ilike(f'%{search}%')))
    users = query.order_by(User.created_at.desc()).all()
    return render_template('users/list.html', users=users, search=search)


@user_bp.route('/new', methods=['GET', 'POST'])
@login_required
@admin_required
def create_user():
    form = RegisterForm()
    if form.validate_on_submit():
        user = User(
            name=form.name.data.strip(),
            email=form.email.data.strip().lower(),
            password_hash=generate_password_hash(form.password.data),
            is_admin=False,
        )
        db.session.add(user)
        db.session.commit()
        flash('User created successfully.', 'success')
        return redirect(url_for('user.list_users'))
    return render_template('users/create.html', form=form)


@user_bp.route('/<int:user_id>')
@login_required
@admin_required
def detail_user(user_id):
    user = User.query.get_or_404(user_id)
    return render_template('users/detail.html', user=user)


@user_bp.route('/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        user.name = request.form.get('name', user.name).strip()
        user.email = request.form.get('email', user.email).strip().lower()
        if request.form.get('password'):
            user.password_hash = generate_password_hash(request.form['password'])
        db.session.commit()
        flash('User updated.', 'success')
        return redirect(url_for('user.detail_user', user_id=user.id))
    return render_template('users/edit.html', user=user)


@user_bp.route('/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot delete your own account from this screen.', 'warning')
        return redirect(url_for('user.detail_user', user_id=user.id))
    db.session.delete(user)
    db.session.commit()
    flash('User deleted.', 'success')
    return redirect(url_for('user.list_users'))
