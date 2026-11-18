from functools import wraps

from flask import abort, redirect, request, url_for
from flask_login import current_user


def admin_required(view_func):
    """
    Decorator that ensures:
    - Unauthenticated users are redirected to login with next parameter.
    - Authenticated non-admin users receive HTTP 403 Forbidden.
    - Admins can proceed.
    """
    @wraps(view_func)
    def decorated_view(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login', next=request.url))
        if not current_user.is_admin:
            abort(403)
        return view_func(*args, **kwargs)

    return decorated_view
