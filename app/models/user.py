from datetime import datetime, timezone

from flask_login import UserMixin

from app.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    library_entries = db.relationship('LibraryEntry', back_populates='user', cascade='all, delete-orphan')
    reading_progress = db.relationship('ReadingProgress', back_populates='user', cascade='all, delete-orphan')
    comments = db.relationship('Comment', back_populates='user', cascade='all, delete-orphan')
    admin_logs = db.relationship('AdminLog', back_populates='admin_user')

    @property
    def role(self):
        return 'admin' if self.is_admin else 'user'

    @role.setter
    def role(self, value):
        self.is_admin = (value == 'admin')

    def __repr__(self):
        return f'<User {self.name}>'
