import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import event
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.observability import current_client_ip, current_request_id


logger = logging.getLogger(__name__)


_SENSITIVE_KEYS = {
    "password",
    "hashed_password",
    "new_password",
    "current_password",
    "token",
    "access_token",
    "refresh_token",
    "reset_token",
    "otp",
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

    if hasattr(value, "value") and isinstance(getattr(value, "value"), (str, int)):
        return value.value  # Enum members

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return str(value)


# ── Tamper evidence ───────────────────────────────────────────────────────────
def _canonical_timestamp(value: Optional[datetime]) -> Optional[str]:
    """Database-independent timestamp form (SQLite drops tzinfo, Postgres keeps it)."""
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.strftime("%Y-%m-%dT%H:%M:%S.%f")


def compute_entry_hash(log: models.AuditLog) -> str:
    content = {
        "user_id": log.user_id,
        "username": log.username,
        "role": log.role,
        "action": log.action,
        "resource_type": log.resource_type,
        "resource_id": log.resource_id,
        "details": log.details,
        "status": log.status,
        "reason": log.reason,
        "ip_address": log.ip_address,
        "request_id": log.request_id,
        "created_at": _canonical_timestamp(log.created_at),
    }
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), default=str)
    return hmac.new(settings.secret_key.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_audit_log(db: Session, limit: Optional[int] = None) -> dict:
    """Recompute every entry HMAC and report rows that no longer match."""
    query = db.query(models.AuditLog).order_by(models.AuditLog.id)
    if limit:
        query = query.limit(limit)
    checked = 0
    unsigned = 0
    mismatched = []
    previous_id = None
    gaps = []
    for log in query.yield_per(500):
        checked += 1
        if previous_id is not None and log.id != previous_id + 1:
            gaps.append({"after_id": previous_id, "next_id": log.id})
        previous_id = log.id
        if not log.entry_hash:
            unsigned += 1
            continue
        if not hmac.compare_digest(log.entry_hash, compute_entry_hash(log)):
            mismatched.append(log.id)
    return {
        "checked": checked,
        "unsigned_legacy_entries": unsigned,
        "tampered_entry_ids": mismatched[:100],
        "tampered_count": len(mismatched),
        "id_gaps": gaps[:100],
        "intact": not mismatched,
        "note": "ID gaps can come from rolled-back transactions; investigate them rather than treating them as proof of deletion.",
    }


@event.listens_for(Session, "before_flush")
def _audit_log_is_append_only(session: Session, flush_context, instances) -> None:
    """Application-level guard; the database triggers are the second line of defence."""
    for obj in session.dirty:
        if isinstance(obj, (models.AuditLog, models.AIPredictionReview)) and session.is_modified(obj):
            raise PermissionError(f"{type(obj).__name__} records are append-only")
    for obj in session.deleted:
        if isinstance(obj, (models.AuditLog, models.AIPredictionReview)):
            raise PermissionError(f"{type(obj).__name__} records are append-only")


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
    *,
    actor: Optional[models.User] = None,
    commit: bool = True,
):
    """Persist a structured audit event without storing credentials or unnecessary PII.

    Pass ``commit=False`` to add the event to the caller's transaction so the
    business change and its audit record are committed (or rolled back) together.
    """

    if actor is not None:
        user_id = user_id if user_id is not None else actor.id
        username = username or actor.username
        role = role or actor.role
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
        ip_address=ip_address or current_client_ip(),
        request_id=current_request_id(),
        created_at=datetime.now(timezone.utc),
    )
    log.entry_hash = compute_entry_hash(log)

    db.add(log)
    if commit:
        db.commit()
        db.refresh(log)
    else:
        db.flush()

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
    dedup_key: Optional[str] = None,
    dedup_window_hours: int = 24,
):
    """Persist a notification and attempt best-effort real-time delivery.

    When ``dedup_key`` is given, an identical alert raised for the same
    recipient within ``dedup_window_hours`` is not duplicated.
    """

    if dedup_key:
        since = datetime.now(timezone.utc) - timedelta(hours=dedup_window_hours)
        existing = db.query(models.Notification).filter(
            models.Notification.dedup_key == dedup_key,
            models.Notification.target_role.is_(target_role) if target_role is None else models.Notification.target_role == target_role,
            models.Notification.target_user_id.is_(target_user_id) if target_user_id is None else models.Notification.target_user_id == target_user_id,
            models.Notification.created_at >= since,
        ).first()
        if existing:
            return existing

    notif = models.Notification(
        title=title,
        message=message,
        notification_type=notification_type,
        target_role=target_role,
        target_user_id=target_user_id,
        related_criminal_id=related_criminal_id,
        related_case_id=related_case_id,
        dedup_key=dedup_key,
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
