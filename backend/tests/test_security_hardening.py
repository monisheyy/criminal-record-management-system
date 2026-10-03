"""Session, lockout, revocation, CSRF, rate-limit and configuration hardening."""
import uuid

import pytest

from app import models
from app.database import SessionLocal
from app.security import get_password_hash, SESSION_COOKIE_NAME


def _make_user(role=models.UserRole.record_clerk, password="CorrectHorse!42", **extra):
    username = f"u_{uuid.uuid4().hex[:10]}"
    db = SessionLocal()
    try:
        user = models.User(username=username, email=f"{username}@example.test", full_name="Test Person",
                           hashed_password=get_password_hash(password), role=role, **extra)
        db.add(user)
        db.commit()
        return username, password, user.id
    finally:
        db.close()


def _login(client, username, password):
    response = client.post("/api/auth/login", data={"username": username, "password": password})
    client.cookies.clear()
    return response


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_account_locks_after_repeated_failures_and_admin_can_unlock(client, admin_token):
    username, password, user_id = _make_user()
    for _ in range(5):
        assert _login(client, username, "wrong-password").status_code == 401
    # Correct password is refused while locked, with the same generic message.
    locked = _login(client, username, password)
    assert locked.status_code == 401
    assert "temporarily locked" in locked.json()["detail"]

    r = client.put(f"/api/admin/users/{user_id}", json={"unlock": True}, headers=_bearer(admin_token))
    assert r.status_code == 200
    assert _login(client, username, password).status_code == 200


def test_unknown_user_and_wrong_password_get_identical_errors(client):
    username, _, _ = _make_user()
    a = _login(client, "no-such-user-xyz", "whatever-password")
    b = _login(client, username, "wrong-password")
    assert a.status_code == b.status_code == 401
    assert a.json()["detail"] == b.json()["detail"]


def test_logout_revokes_the_presented_token(client):
    username, password, _ = _make_user()
    token = _login(client, username, password).json()["access_token"]
    assert client.get("/api/auth/me", headers=_bearer(token)).status_code == 200
    assert client.post("/api/auth/logout", headers=_bearer(token)).status_code == 200
    assert client.get("/api/auth/me", headers=_bearer(token)).status_code == 401


def test_forced_password_change_blocks_other_endpoints_until_changed(client):
    username, password, _ = _make_user(must_change_password=True)
    login = _login(client, username, password)
    assert login.status_code == 200
    assert login.json()["user"]["must_change_password"] is True
    token = login.json()["access_token"]

    blocked = client.get("/api/criminals", headers=_bearer(token))
    assert blocked.status_code == 403
    assert blocked.headers.get("X-Password-Change-Required") == "true"
    assert client.get("/api/auth/me", headers=_bearer(token)).status_code == 200

    weak = client.post("/api/auth/change-password", json={"current_password": password, "new_password": "password123"},
                       headers=_bearer(token))
    assert weak.status_code == 422

    changed = client.post("/api/auth/change-password",
                          json={"current_password": password, "new_password": "A-much-better-passphrase"},
                          headers=_bearer(token))
    client.cookies.clear()
    assert changed.status_code == 200
    new_token = changed.json()["access_token"]
    # The old session is invalidated; the newly issued one works everywhere.
    assert client.get("/api/auth/me", headers=_bearer(token)).status_code == 401
    assert client.get("/api/criminals", headers=_bearer(new_token)).status_code == 200


def test_admin_role_change_and_deactivation_invalidate_sessions(client, admin_token):
    username, password, user_id = _make_user(role=models.UserRole.investigating_officer)
    token = _login(client, username, password).json()["access_token"]
    assert client.get("/api/auth/me", headers=_bearer(token)).status_code == 200
    r = client.put(f"/api/admin/users/{user_id}", json={"role": "record_clerk"}, headers=_bearer(admin_token))
    assert r.status_code == 200
    assert client.get("/api/auth/me", headers=_bearer(token)).status_code == 401


def test_admin_cannot_demote_or_deactivate_self(client, admin_token):
    me = client.get("/api/auth/me", headers=_bearer(admin_token)).json()
    r = client.put(f"/api/admin/users/{me['id']}", json={"is_active": False}, headers=_bearer(admin_token))
    assert r.status_code == 409
    r = client.put(f"/api/admin/users/{me['id']}", json={"role": "record_clerk"}, headers=_bearer(admin_token))
    assert r.status_code == 409


def test_admin_created_users_must_change_password_and_weak_passwords_rejected(client, admin_token):
    base = {"username": f"new_{uuid.uuid4().hex[:6]}", "email": f"{uuid.uuid4().hex[:6]}@example.com",
            "full_name": "New Starter", "role": "record_clerk"}
    weak = client.post("/api/admin/users", json={**base, "password": "admin123"}, headers=_bearer(admin_token))
    assert weak.status_code == 422
    ok = client.post("/api/admin/users", json={**base, "password": "Temporary-Pass-2026"}, headers=_bearer(admin_token))
    assert ok.status_code == 200, ok.text
    assert ok.json()["must_change_password"] is True


def test_cookie_session_is_httponly_and_unsafe_methods_need_csrf_header(client):
    username, password, _ = _make_user(role=models.UserRole.admin)
    response = client.post("/api/auth/login", data={"username": username, "password": password})
    assert response.status_code == 200
    set_cookie = response.headers.get("set-cookie", "")
    assert SESSION_COOKIE_NAME in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "samesite=strict" in set_cookie.lower()
    try:
        assert client.get("/api/auth/me").status_code == 200  # cookie-authenticated read
        no_header = client.post("/api/notifications/read-all")
        assert no_header.status_code == 403
        with_header = client.post("/api/notifications/read-all", headers={"X-Requested-With": "XMLHttpRequest"})
        assert with_header.status_code == 200
        out = client.post("/api/auth/logout", headers={"X-Requested-With": "XMLHttpRequest"})
        assert out.status_code == 200
    finally:
        client.cookies.clear()
    assert client.get("/api/auth/me").status_code == 401


def test_login_rate_limit_returns_429(client, monkeypatch):
    from app.utils import rate_limit

    monkeypatch.setattr(rate_limit, "auth_rate_limiter", rate_limit.SlidingWindowRateLimiter(limit=2))
    codes = [_login(client, "nobody-at-all", "irrelevant-password").status_code for _ in range(3)]
    assert codes[:2] == [401, 401]
    assert codes[2] == 429


def test_security_headers_and_request_id(client):
    r = client.get("/api/health", headers={"X-Request-ID": "trace-abc-12345"})
    assert r.headers["X-Request-ID"] == "trace-abc-12345"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    generated = client.get("/api/health").headers["X-Request-ID"]
    assert len(generated) == 32


def test_validation_errors_do_not_echo_submitted_values(client, admin_token):
    secret_value = "javascript:alert('pii-123-45-6789')"
    r = client.post("/api/criminals", json={"first_name": "Valid", "last_name": "Name", "photo_url": secret_value},
                    headers=_bearer(admin_token))
    assert r.status_code == 422
    assert "pii-123-45-6789" not in r.text
    assert r.json()["request_id"]


def test_readiness_reports_schema_at_head(client):
    r = client.get("/api/health/ready")
    assert r.status_code == 200
    assert r.json()["checks"] == {"database": "ok", "schema": "ok"}


@pytest.mark.parametrize("overrides, message", [
    ({"CORS_ORIGINS": ""}, "CORS_ORIGINS must be set"),
    ({"CORS_ORIGINS": "http://insecure.example"}, "HTTPS"),
    ({"SEED_DEMO_DATA": "true"}, "SEED_DEMO_DATA"),
    ({"RECOVERY_PROVIDER": "dev"}, "RECOVERY_PROVIDER"),
    ({"COOKIE_SECURE": "false"}, "COOKIE_SECURE"),
    ({"TRUSTED_HOSTS": "*"}, "TRUSTED_HOSTS"),
    ({"AI_ALLOW_SYNTHETIC_MODELS": "true"}, "AI_ALLOW_SYNTHETIC_MODELS"),
])
def test_production_configuration_refuses_unsafe_settings(monkeypatch, overrides, message):
    from app import config

    safe = {
        "APP_ENV": "production", "SECRET_KEY": "x" * 48, "CORS_ORIGINS": "https://crms.example.gov",
        "SEED_DEMO_DATA": "false", "RECOVERY_PROVIDER": "smtp", "COOKIE_SECURE": "true",
        "TRUSTED_HOSTS": "crms.example.gov", "AI_ALLOW_SYNTHETIC_MODELS": "false",
    }
    for key, value in {**safe, **overrides}.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(RuntimeError, match=message):
        config._load_settings()


def test_production_configuration_accepts_safe_settings(monkeypatch):
    from app import config

    for key, value in {
        "APP_ENV": "production", "SECRET_KEY": "x" * 48, "CORS_ORIGINS": "https://crms.example.gov",
        "SEED_DEMO_DATA": "false", "RECOVERY_PROVIDER": "smtp", "COOKIE_SECURE": "true",
        "TRUSTED_HOSTS": "crms.example.gov", "AI_ALLOW_SYNTHETIC_MODELS": "false",
    }.items():
        monkeypatch.setenv(key, value)
    loaded = config._load_settings()
    assert loaded.is_production and not loaded.enable_api_docs and loaded.cookie_secure


def test_known_demo_credentials_are_disabled_in_production_startup():
    from app.main import disable_known_demo_credentials

    db = SessionLocal()
    try:
        existing = db.query(models.User).filter(models.User.username == "officer2").first()
        if existing is None:
            db.add(models.User(username="officer2", email="officer2@demo.test", full_name="Demo Officer",
                               hashed_password=get_password_hash("officer123"),
                               role=models.UserRole.investigating_officer))
            db.commit()
        assert disable_known_demo_credentials(db) >= 1
        user = db.query(models.User).filter(models.User.username == "officer2").first()
        assert user.is_active is False
    finally:
        db.close()
