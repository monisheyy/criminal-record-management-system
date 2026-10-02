from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List
from jose import JWTError, jwt

from app.database import get_db, SessionLocal
from app import models, schemas
from app.security import require_any_role, SECRET_KEY, ALGORITHM
from app.utils.notification_realtime import notification_manager

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _notification_visible_to_user(notification: models.Notification, user: models.User) -> bool:
    return (
        notification.target_user_id == user.id
        or notification.target_role == user.role.value
        or notification.target_role is None
    )


def _notification_payload(notification: models.Notification) -> dict:
    return {
        "event": "notification.created",
        "notification": {
            "id": notification.id,
            "title": notification.title,
            "message": notification.message,
            "notification_type": notification.notification_type,
            "is_read": notification.is_read,
            "related_criminal_id": notification.related_criminal_id,
            "related_case_id": notification.related_case_id,
            "created_at": notification.created_at.isoformat() if notification.created_at else None,
        },
    }


@router.get("", response_model=List[schemas.NotificationOut])
async def list_notifications(
    unread_only: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    q = db.query(models.Notification).filter(
        or_(
            models.Notification.target_role == current_user.role.value,
            models.Notification.target_role.is_(None),
            models.Notification.target_user_id == current_user.id,
        )
    )
    if unread_only:
        q = q.filter(models.Notification.is_read.is_(False))
    return q.order_by(models.Notification.created_at.desc()).offset(skip).limit(limit).all()


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    notif = db.query(models.Notification).filter(models.Notification.id == notification_id).first()
    if not notif or not _notification_visible_to_user(notif, current_user):
        return {"message": "Marked as read"}
    notif.is_read = True
    db.commit()
    return {"message": "Marked as read"}


@router.post("/read-all")
async def mark_all_read(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    db.query(models.Notification).filter(
        or_(
            models.Notification.target_role == current_user.role.value,
            models.Notification.target_user_id == current_user.id,
            models.Notification.target_role.is_(None),
        ),
        models.Notification.is_read.is_(False),
    ).update({"is_read": True}, synchronize_session=False)
    db.commit()
    return {"message": "All notifications marked as read"}


async def _authenticate_websocket(websocket: WebSocket, db: Session):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username or payload.get("type") not in (None, "access"):
            raise JWTError()
    except JWTError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None or not user.is_active or user.role.value not in {"admin", "investigating_officer", "record_clerk"}:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None
    return user


@router.websocket("/ws")
async def notification_websocket(websocket: WebSocket):
    """Authenticated per-user/role notification stream.

    Browser WebSocket clients pass the existing JWT as ?token=... because the
    WebSocket API does not permit arbitrary Authorization headers.
    """
    db = SessionLocal()
    user = None
    try:
        user = await _authenticate_websocket(websocket, db)
        if not user:
            return
        await notification_manager.connect(websocket, user.id, user.role.value)
        await websocket.send_json({"event": "notification.connected"})
        while True:
            # Keep the connection alive and permit the client to send a ping/close.
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_json({"event": "notification.pong"})
    except WebSocketDisconnect:
        pass
    finally:
        if user:
            await notification_manager.disconnect(websocket, user.id, user.role.value)
        db.close()
