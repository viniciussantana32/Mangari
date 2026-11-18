from datetime import datetime, timezone

from app.extensions import db


class CommentReport(db.Model):
    __tablename__ = 'comment_reports'

    id = db.Column(db.Integer, primary_key=True)
    comment_id = db.Column(db.Integer, db.ForeignKey('comments.id', ondelete='CASCADE'), nullable=False)
    reporter_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    comment = db.relationship('Comment', back_populates='reports')
    reporter = db.relationship('User', foreign_keys=[reporter_id])

    def __repr__(self):
        return f'<CommentReport {self.id} for Comment {self.comment_id}>'
