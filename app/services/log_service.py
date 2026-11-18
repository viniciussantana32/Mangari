from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.admin_log import AdminLog


def log_action(admin_id, action, entity_type, entity_id=None, description=""):
    """
    Registra uma ação administrativa com segurança no banco de dados.
    """
    try:
        log = AdminLog(
            admin_user_id=admin_id,
            action=str(action),
            entity_type=str(entity_type),
            entity_id=entity_id,
            description=str(description),
        )
        db.session.add(log)
        db.session.commit()
        return log
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception('Falha ao registrar log administrativo.')
        return None
