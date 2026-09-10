from sqlalchemy.orm import Session
from app import models
from datetime import datetime


def create_audit_log(
    db: Session,
    action: str,
    user_id: int = None,
    username: str = None,
    resource_type: str = None,
    resource_id: int = None,
    details: dict = None,
    ip_address: str = None
):
    log = models.AuditLog(
        user_id=user_id,
        username=username,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
    )
    db.add(log)
    db.commit()
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
    notif = models.Notification(
        title=title,
        message=message,
        notification_type=notification_type,
        target_role=target_role,
        target_user_id=target_user_id,
        related_criminal_id=related_criminal_id,
        related_case_id=related_case_id,
    )
    db.add(notif)
    db.commit()
    return notif
