from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models.user import User


def create_user(name, email, password, is_admin=False):
    user = User(
        name=name.strip(),
        email=email.strip().lower(),
        password_hash=generate_password_hash(password),
        is_admin=is_admin,
    )
    db.session.add(user)
    db.session.commit()
    return user
