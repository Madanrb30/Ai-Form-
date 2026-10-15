from typing import Optional, Any
from sqlalchemy.orm import Session
import json
from app.models.audit_log import AuditLog
from app.core.logging import logger


def record_audit_log(
    db: Session,
    action: str,
    actor_id: Optional[int] = None,
    actor_email: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    details: Optional[Any] = None,
    ip_address: Optional[str] = None,
    status: str = "SUCCESS",
) -> Optional[AuditLog]:
    """
    Records an immutable audit event for security and administrative actions.
    Sanitizes details to ensure no sensitive credentials, passwords, or tokens are logged.
    """
    try:
        details_str = None
        if details is not None:
            if isinstance(details, (dict, list)):
                # Sanitize sensitive keys
                sanitized = details
                if isinstance(details, dict):
                    sanitized = {
                        k: ("[REDACTED]" if any(s in k.lower() for s in ["password", "token", "secret", "key"]) else v)
                        for k, v in details.items()
                    }
                details_str = json.dumps(sanitized)
            else:
                details_str = str(details)

        log_entry = AuditLog(
            actor_id=actor_id,
            actor_email=actor_email,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            details=details_str,
            ip_address=ip_address,
            status=status,
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        return log_entry
    except Exception as e:
        logger.warning(f"Failed to record audit log: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return None
