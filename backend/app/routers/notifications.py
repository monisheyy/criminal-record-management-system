from typing import List

from fastapi import APIRouter, Depends, Query, Response, WebSocket, WebSocketDisconnect, status
from jwt import PyJWTError as JWTError
from sqlalchemy import and_, exists, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db, SessionLocal
from app import models, schemas
from app.security import SESSION_COOKIE_NAME, require_any_role, resolve_token_user
from app.utils.notification_realtime import notification_manager
from app.utils.pagination import MAX_PAGE_SIZE, paginate

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _visible_filter(user: models.User):
    return or_(
        models.Notification.target_user_id == user.id,
        and_(models.Notification.target_user_id.is_(None), models.Notification.target_role == user.role.value),
        and_(models.Notification.target_user_id.is_(None), models.Notification.target_role.is_(None)),
    )


def _read_by_user(user: models.User):
    return exists().where(
        models.NotificationRead.notification_id == models.Notification.id,
        models.NotificationRead.user_id == user.id,
    )


def _notification_visible_to_user(notification: models.Notification, user: models.User) -> bool:
    if notification.target_user_id is not None:
        return notification.target_user_id == user.id
    return notification.target_role in (None, user.role.value)


def _notification_payload(notification: models.Notification) -> dict:
    return {
        "event": "notification.created",
        "notification": {
            "id": notification.id,
            "title": notification.title,
            "message": notification.message,
            "notification_type": notification.notification_type,
            "is_read": False,
            "related_criminal_id": notification.related_criminal_id,
            "related_case_id": notification.related_case_id,
            "created_at": notification.created_at.isoformat() if notification.created_at else None,
        },
    }


@router.get("", response_model=List[schemas.NotificationOut])
async def list_notifications(
    response: Response,
    unread_only: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    """Notifications visible to the caller, with per-user read state."""
    read_flag = _read_by_user(current_user)
    q = db.query(models.Notification, read_flag.label("read_by_me")).filter(_visible_filter(current_user))
    if unread_only:
        q = q.filter(~read_flag)
    unread = db.query(models.Notification.id).filter(_visible_filter(current_user), ~read_flag).count()
    response.headers["X-Unread-Count"] = str(unread)
    rows = paginate(q.order_by(models.Notification.created_at.desc(), models.Notification.id.desc()), response, skip, limit)
    return [
        schemas.NotificationOut(
            id=n.id, title=n.title, message=n.message, notification_type=n.notification_type,
            is_read=bool(read), related_criminal_id=n.related_criminal_id,
            related_case_id=n.related_case_id, created_at=n.created_at,
        )
        for n, read in rows
    ]


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    notif = db.query(models.Notification).filter(models.Notification.id == notification_id).first()
    # Identical response for missing and foreign notifications (no existence oracle).
    if notif and _notification_visible_to_user(notif, current_user):
        already = db.query(models.NotificationRead.id).filter(
            models.NotificationRead.notification_id == notification_id,
            models.NotificationRead.user_id == current_user.id,
        ).first()
        if not already:
            db.add(models.NotificationRead(notification_id=notification_id, user_id=current_user.id))
            db.commit()
    return {"message": "Marked as read"}


@router.post("/read-all")
async def mark_all_read(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    unread_ids = [row.id for row in db.query(models.Notification.id).filter(
        _visible_filter(current_user), ~_read_by_user(current_user)
    ).all()]
    for notification_id in unread_ids:
        db.add(models.NotificationRead(notification_id=notification_id, user_id=current_user.id))
    db.commit()
    return {"message": "All notifications marked as read", "marked": len(unread_ids)}


def _origin_allowed(websocket: WebSocket) -> bool:
    """Block cross-site WebSocket hijacking: browsers always send Origin."""
    origin = websocket.headers.get("origin")
    if origin is None:
        return True  # non-browser clients (tests, scripts) authenticate explicitly
    return origin in settings.cors_origins


async def _authenticate_websocket(websocket: WebSocket, db: Session):
    if not _origin_allowed(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None
    # Prefer the HttpOnly session cookie; ?token= is kept for API clients.
    token = websocket.cookies.get(SESSION_COOKIE_NAME) or websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None
    try:
        user, _ = resolve_token_user(db, token)
    except JWTError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None
    if user.must_change_password:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None
    return user


@router.websocket("/ws")
async def notification_websocket(websocket: WebSocket):
    """Authenticated per-user/role notification stream."""
    db = SessionLocal()
    user = None
    try:
        user = await _authenticate_websocket(websocket, db)
        if not user:
            return
        await notification_manager.connect(websocket, user.id, user.role.value)
        await websocket.send_json({"event": "notification.connected"})
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_json({"event": "notification.pong"})
    except WebSocketDisconnect:
        pass
    finally:
        if user:
            await notification_manager.disconnect(websocket, user.id, user.role.value)
        db.close()
