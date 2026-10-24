import logging
import uuid

from sqlalchemy.orm import Session

from app.db.models import AuditEvent

logger = logging.getLogger(__name__)


def record_audit(
    session: Session,
    action: str,
    *,
    actor_id: str | None,
    outcome: str = "success",
    resource_type: str | None = None,
    resource_id: str | None = None,
    detail: str | None = None,
) -> None:
    """Write an audit event. A failure to write is logged but never breaks the request."""
    try:
        session.add(
            AuditEvent(
                event_id=f"ev_{uuid.uuid4().hex}",
                actor_id=actor_id,
                action=action,
                outcome=outcome,
                resource_type=resource_type,
                resource_id=resource_id,
                detail=detail[:255] if detail else None,
            )
        )
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Could not write audit event %s", action)
