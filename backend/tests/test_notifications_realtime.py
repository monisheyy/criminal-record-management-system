
import asyncio
from unittest.mock import AsyncMock

from app import models
from app.utils.notification_realtime import NotificationConnectionManager
from app.utils.audit import create_notification


def test_notification_persists_and_targets_role(db_session):
    """Verify that a notification is saved and linked to a valid case."""

    # 1. Create a valid user.
    user = models.User(
        username="notify-user",
        email="notify-user@example.test",
        full_name="Notification Test User",
        hashed_password="test-hash",
        role=models.UserRole.investigating_officer,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    # 2. Create a real case so the foreign key is valid.
    case = models.Case(
        case_number="NOTIFY-TEST-CASE-001",
        title="Notification Test Case",
        assigned_officer_id=user.id,
    )
    db_session.add(case)
    db_session.flush()

    # 3. Create a notification linked to the real case.
    notif = create_notification(
        db_session,
        title="Case assigned",
        message="A case was assigned",
        target_role="investigating_officer",
        related_case_id=case.id,
    )

    # 4. Verify that the notification was persisted correctly.
    assert notif.id is not None
    assert notif.title == "Case assigned"
    assert notif.message == "A case was assigned"
    assert notif.target_role == "investigating_officer"
    assert notif.related_case_id == case.id

    # 5. Verify that the notification can be retrieved from the database.
    saved_notification = (
        db_session.query(models.Notification)
        .filter(models.Notification.id == notif.id)
        .one()
    )
    assert saved_notification.related_case_id == case.id
    assert saved_notification.target_role == "investigating_officer"


def test_notification_manager_delivers_to_target_user():
    """Verify that a notification reaches the intended connected user."""

    async def run():
        manager = NotificationConnectionManager()
        ws = AsyncMock()

        await manager.connect(ws, user_id=10, role="admin")

        payload = {"event": "notification.created"}
        await manager.broadcast(payload, target_user_id=10)

        ws.send_json.assert_awaited_once_with(payload)

        await manager.disconnect(ws, 10, "admin")

    asyncio.run(run())


def test_notification_manager_does_not_deliver_to_other_user():
    """Verify that a notification is not sent to the wrong user."""

    async def run():
        manager = NotificationConnectionManager()
        ws = AsyncMock()

        await manager.connect(ws, user_id=10, role="admin")

        payload = {"event": "notification.created"}
        await manager.broadcast(payload, target_user_id=11)

        ws.send_json.assert_not_awaited()

        await manager.disconnect(ws, 10, "admin")

    asyncio.run(run())
