
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app import models


logger = logging.getLogger(__name__)


_SENSITIVE_KEYS = {
    "password",
    "hashed_password",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "jwt",
    "authorization",
    "phone",
    "email",
    "address",
    "fingerprint_id",
    "photo_url",
    "file_url",
    "statement",
    "complainant_contact",
}


def _safe_metadata(value: Any) -> Any:
    """Remove credentials and high-sensitivity PII from audit metadata."""

    if isinstance(value, dict):
        return {
            key: (
                "[REDACTED]"
                if key.lower() in _SENSITIVE_KEYS
                else _safe_metadata(item)
            )
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [_safe_metadata(item) for item in value]

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return str(value)


def create_audit_log(
    db: Session,
    action: str,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    role: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
    status: str = "success",
    reason: Optional[str] = None,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
):
    """Persist a structured audit event without storing credentials or unnecessary PII."""

    if hasattr(role, "value"):
        role = role.value

    log = models.AuditLog(
        user_id=user_id,
        username=username,
        role=role,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        status=status,
        reason=reason,
        details=_safe_metadata(details or {}),
        ip_address=ip_address,
    )

    db.add(log)
    db.commit()
    db.refresh(log)

    return log


def create_notification(
    db: Session,
    title: str,
    message: str,
    notification_type: str = "info",
    target_role: str = None,
    target_user_id: int = None,
    related_criminal_id: int = None,
    related_case_id: int = None,
):
    """Persist a notification and attempt best-effort real-time delivery."""

    notif = models.Notification(
        title=title,
        message=message,
        notification_type=notification_type,
        target_role=target_role,
        target_user_id=target_user_id,
        related_criminal_id=related_criminal_id,
        related_case_id=related_case_id,
    )

    # Persist the notification before attempting WebSocket delivery.
    db.add(notif)
    db.commit()
    db.refresh(notif)

    # Real-time delivery is best-effort. The database remains the
    # source of truth if no event loop or WebSocket connection is available.
    try:
        import asyncio

        from app.utils.notification_realtime import (
            notification_manager,
            _notification_payload,
        )

        loop = asyncio.get_running_loop()

        loop.create_task(
            notification_manager.broadcast(
                _notification_payload(notif),
                target_user_id=target_user_id,
                target_role=target_role,
            )
        )

    except RuntimeError:
        # Synchronous callers may not have a running event loop.
        pass

    except Exception:
        # A delivery scheduling problem must not hide a saved notification.
        logger.exception(
            "Real-time delivery could not be scheduled for notification ID %s",
            notif.id,
        )

    return notif
