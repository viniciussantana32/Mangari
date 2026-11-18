from datetime import datetime, timezone

from app.extensions import db


class AdminLog(db.Model):
    __tablename__ = 'admin_logs'

    id = db.Column(db.Integer, primary_key=True)
    admin_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(50), nullable=False)
    entity_id = db.Column(db.Integer, nullable=True)
    description = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    admin_user = db.relationship('User', back_populates='admin_logs', foreign_keys=[admin_user_id])

    def __repr__(self):
        return f'<AdminLog {self.action} on {self.entity_type} #{self.entity_id}>'
