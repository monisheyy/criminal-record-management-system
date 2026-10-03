"""Role and object-level authorization coverage for sensitive endpoints."""
import re
import uuid

import pytest

from app import models
from app.database import SessionLocal
from app.main import app
from app.security import get_password_hash

PUBLIC_PATHS = {
    "/api/health", "/api/health/ready", "/api/auth/login", "/api/auth/logout",
    "/api/auth/password-recovery/request", "/api/auth/password-recovery/verify",
    "/api/auth/password-recovery/reset",
}


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _protected_routes():
    # The OpenAPI schema lists every HTTP route regardless of how FastAPI
    # nests included routers internally (this changed between versions).
    for path, operations in app.openapi()["paths"].items():
        if path.startswith("/api/") and path not in PUBLIC_PATHS:
            for method in sorted(operations):
                yield method.upper(), path


PROTECTED_ROUTES = list(_protected_routes())


def test_route_inventory_is_not_empty():
    # Guards against the matrix below silently collecting zero cases.
    assert len(PROTECTED_ROUTES) >= 40, PROTECTED_ROUTES


@pytest.mark.parametrize("method,path", PROTECTED_ROUTES)
def test_every_protected_route_rejects_anonymous_requests(client, method, path):
    concrete = re.sub(r"\{[^}]+\}", "1", path)
    client.cookies.clear()
    response = client.request(method, concrete)
    assert response.status_code == 401, f"{method} {path} returned {response.status_code}"


def _officer(name_hint="other"):
    username = f"off_{name_hint}_{uuid.uuid4().hex[:6]}"
    db = SessionLocal()
    try:
        user = models.User(username=username, email=f"{username}@example.test", full_name=f"Officer {name_hint.title()}",
                           hashed_password=get_password_hash("Officer-Pass-2026"),
                           role=models.UserRole.investigating_officer)
        db.add(user)
        db.commit()
        return user.id
    finally:
        db.close()


def _login(client, username, password):
    token = client.post("/api/auth/login", data={"username": username, "password": password}).json()["access_token"]
    client.cookies.clear()
    return token


@pytest.fixture
def foreign_case(client, admin_token):
    """A case assigned to a *different* officer than officer_test."""
    other_id = _officer()
    case = client.post("/api/cases", json={"title": "Foreign Case", "crime_type": "Fraud",
                                           "assigned_officer_id": other_id}, headers=_bearer(admin_token))
    assert case.status_code == 200, case.text
    return case.json()


@pytest.mark.parametrize("method,suffix,body", [
    ("GET", "", None),
    ("PUT", "", {"title": "Hijacked"}),
    ("GET", "/report", None),
    ("GET", "/report/excel", None),
    ("POST", "/evidence", {"type": "digital", "description": "Planted evidence"}),
    ("POST", "/victims", {"first_name": "Some", "last_name": "Person"}),
    ("POST", "/criminals", {"criminal_id": 1, "role": "suspect"}),
    ("POST", "/assign", {"officer_id": 1}),
])
def test_officer_cannot_touch_case_assigned_to_another_officer(client, officer_token, foreign_case, method, suffix, body):
    r = client.request(method, f"/api/cases/{foreign_case['id']}{suffix}", json=body, headers=_bearer(officer_token))
    assert r.status_code == 403, f"{method} {suffix}: {r.status_code} {r.text}"


def test_officer_cannot_assign_case_to_someone_else(client, admin_token, officer_token):
    case = client.post("/api/cases", json={"title": "Unassigned Case", "crime_type": "Arson"}, headers=_bearer(admin_token)).json()
    other_id = _officer("target")
    r = client.post(f"/api/cases/{case['id']}/assign", json={"officer_id": other_id}, headers=_bearer(officer_token))
    assert r.status_code == 403


def test_assignment_requires_active_investigating_officer(client, admin_token):
    case = client.post("/api/cases", json={"title": "Assignment Target", "crime_type": "Arson"}, headers=_bearer(admin_token)).json()
    clerk_id = client.get("/api/auth/me", headers=_bearer(admin_token)).json()["id"]  # an admin, not an officer
    r = client.post(f"/api/cases/{case['id']}/assign", json={"officer_id": clerk_id}, headers=_bearer(admin_token))
    assert r.status_code == 422


def test_clerk_cannot_list_or_run_ai_predictions(client, clerk_token):
    assert client.get("/api/ai/predictions", headers=_bearer(clerk_token)).status_code == 403
    assert client.post("/api/ai/predict", json={"criminal_id": 1}, headers=_bearer(clerk_token)).status_code == 403
    assert client.get("/api/ai/status", headers=_bearer(clerk_token)).status_code == 403


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/admin/users"), ("GET", "/api/admin/audit-logs"), ("GET", "/api/admin/audit-logs/verify"),
    ("GET", "/api/admin/metrics"), ("POST", "/api/ai/retrain"), ("POST", "/api/gangs"),
    ("GET", "/api/admin/settings"),
])
@pytest.mark.parametrize("token_name", ["officer_token", "clerk_token"])
def test_admin_only_endpoints_reject_non_admins(client, request, method, path, token_name):
    token = request.getfixturevalue(token_name)
    r = client.request(method, path, json={}, headers=_bearer(token))
    assert r.status_code == 403, f"{token_name} {method} {path}: {r.status_code}"


def test_clerk_reports_exclude_ai_output(client, admin_token, clerk_token):
    criminal = client.post("/api/criminals", json={"first_name": "Report", "last_name": "Subject", "crime_type": "Fraud"},
                           headers=_bearer(admin_token)).json()
    r = client.get(f"/api/criminals/{criminal['id']}/report", headers=_bearer(clerk_token))
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    logs = client.get("/api/admin/audit-logs", params={"action": "REPORT_GENERATED", "limit": 5}, headers=_bearer(admin_token)).json()
    latest = next(log for log in logs if log["resource_id"] == criminal["id"])
    assert latest["details"]["includes_ai"] is False


def test_notification_read_state_is_per_user(client, admin_token):
    db = SessionLocal()
    try:
        second_admin = models.User(username=f"admin2_{uuid.uuid4().hex[:6]}", email=f"{uuid.uuid4().hex[:6]}@example.test",
                                   full_name="Second Admin", hashed_password=get_password_hash("Second-Admin-2026"),
                                   role=models.UserRole.admin)
        note = models.Notification(title="Role broadcast", message="For all admins", target_role="admin")
        private = models.Notification(title="Private", message="Only for officer_test",
                                      target_user_id=db.query(models.User).filter_by(username="officer_test").one().id)
        db.add_all([second_admin, note, private])
        db.commit()
        note_id, private_id, second_username = note.id, private.id, second_admin.username
    finally:
        db.close()

    second_token = _login(client, second_username, "Second-Admin-2026")
    assert client.post(f"/api/notifications/{note_id}/read", headers=_bearer(admin_token)).status_code == 200

    mine = {n["id"]: n for n in client.get("/api/notifications", headers=_bearer(admin_token)).json()}
    theirs = {n["id"]: n for n in client.get("/api/notifications", headers=_bearer(second_token)).json()}
    assert mine[note_id]["is_read"] is True
    assert theirs[note_id]["is_read"] is False, "one admin's read receipt must not clear it for other admins"
    assert private_id not in mine and private_id not in theirs, "user-targeted notifications are private"
