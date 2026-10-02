
import asyncio
from collections import defaultdict
from datetime import datetime
from typing import Dict, Set

from fastapi import WebSocket


def _notification_payload(notification) -> dict:
    """Convert a database notification into a JSON-serializable event."""

    created_at = getattr(notification, "created_at", None)

    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()

    notification_data = {
        "id": notification.id,
        "title": notification.title,
        "message": notification.message,
        "notification_type": notification.notification_type,
        "is_read": notification.is_read,
        "target_role": notification.target_role,
        "target_user_id": notification.target_user_id,
        "related_criminal_id": notification.related_criminal_id,
        "related_case_id": notification.related_case_id,
        "created_at": created_at,
    }

    return {
        "event": "notification.created",
        "notification": notification_data,
    }


class NotificationConnectionManager:
    """Manage WebSocket connections and deliver targeted notifications."""

    def __init__(self):
        self._connections: Dict[int, Set[WebSocket]] = defaultdict(set)
        self._role_connections: Dict[str, Set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_id: int, role: str):
        await websocket.accept()

        async with self._lock:
            self._connections[user_id].add(websocket)
            self._role_connections[role].add(websocket)

    async def disconnect(self, websocket: WebSocket, user_id: int, role: str):
        async with self._lock:
            self._connections[user_id].discard(websocket)
            self._role_connections[role].discard(websocket)

            if not self._connections[user_id]:
                self._connections.pop(user_id, None)

            if not self._role_connections[role]:
                self._role_connections.pop(role, None)

    async def broadcast(
        self,
        payload: dict,
        target_user_id: int | None = None,
        target_role: str | None = None,
    ):
        async with self._lock:
            sockets = set()

            if target_user_id is not None:
                sockets.update(
                    self._connections.get(target_user_id, set())
                )

            if target_role is not None:
                sockets.update(
                    self._role_connections.get(target_role, set())
                )

            if target_user_id is None and target_role is None:
                sockets = {
                    websocket
                    for group in self._connections.values()
                    for websocket in group
                }

        stale = []

        for websocket in sockets:
            try:
                await websocket.send_json(payload)
            except Exception:
                # Remove connections that can no longer receive messages.
                stale.append(websocket)

        if stale:
            async with self._lock:
                for websocket in stale:
                    for user_id, group in list(self._connections.items()):
                        group.discard(websocket)

                        if not group:
                            self._connections.pop(user_id, None)

                    for role, group in list(self._role_connections.items()):
                        group.discard(websocket)

                        if not group:
                            self._role_connections.pop(role, None)


notification_manager = NotificationConnectionManager()
