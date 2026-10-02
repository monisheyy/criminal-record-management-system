"""Password recovery tests.

These tests use the real API flow and monkeypatch the provider in environments
where the project's full authentication dependencies are installed.
"""
import os
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-at-least-32-bytes-long")

from app import models
from app.security import get_password_hash, verify_password
from app.utils.recovery import generate_otp, hash_secret, secrets_match


def test_otp_is_six_digits_and_hashed():
    otp = generate_otp()
    assert len(otp) == 6 and otp.isdigit()
    stored = hash_secret(otp)
    assert stored != otp
    assert secrets_match(otp, stored)
    assert not secrets_match("000000", stored)


def test_expired_challenge_is_rejected(client, db_session):
    user = models.User(username="recovery_user", email="recovery@example.com", full_name="Recovery User", hashed_password=get_password_hash("oldpassword"), role=models.UserRole.record_clerk, is_active=True)
    db_session.add(user); db_session.commit()
    challenge = models.PasswordRecovery(user_id=user.id, request_ip="127.0.0.1", otp_hash=hash_secret("123456"), otp_expires_at=datetime.utcnow() - timedelta(seconds=1), max_attempts=5)
    db_session.add(challenge); db_session.commit()
    response = client.post("/api/auth/password-recovery/verify", json={"identifier": "recovery_user", "otp": "123456"})
    assert response.status_code == 400


def test_wrong_otp_increments_attempts(client, db_session):
    user = models.User(username="attempt_user", email="attempt@example.com", full_name="Attempt User", hashed_password=get_password_hash("oldpassword"), role=models.UserRole.record_clerk, is_active=True)
    db_session.add(user); db_session.commit()
    challenge = models.PasswordRecovery(user_id=user.id, request_ip="127.0.0.1", otp_hash=hash_secret("123456"), otp_expires_at=datetime.utcnow() + timedelta(minutes=5), max_attempts=2)
    db_session.add(challenge); db_session.commit()
    for _ in range(2):
        response = client.post("/api/auth/password-recovery/verify", json={"identifier": "attempt_user", "otp": "999999"})
        assert response.status_code == 400
    db_session.refresh(challenge)
    assert challenge.attempts == 2
    assert challenge.consumed_at is not None


def test_password_reset_invalidates_old_password(client, db_session):
    old = "oldpassword"
    new = "newpassword123"
    user = models.User(username="reset_user", email="reset@example.com", full_name="Reset User", hashed_password=get_password_hash(old), role=models.UserRole.record_clerk, is_active=True)
    db_session.add(user); db_session.commit()
    challenge = models.PasswordRecovery(user_id=user.id, request_ip="127.0.0.1", otp_hash=hash_secret("123456"), otp_expires_at=datetime.utcnow() + timedelta(minutes=5), max_attempts=5)
    db_session.add(challenge); db_session.commit()
    with patch("app.routers.auth.generate_reset_token", return_value="r" * 43):
        response = client.post("/api/auth/password-recovery/verify", json={"identifier": "reset_user", "otp": "123456"})
    assert response.status_code == 200
    reset_token = response.json()["reset_token"]
    response = client.post("/api/auth/password-recovery/reset", json={"reset_token": reset_token, "new_password": new})
    assert response.status_code == 200
    db_session.refresh(user)
    assert not verify_password(old, user.hashed_password)
    assert verify_password(new, user.hashed_password)
    response = client.post("/api/auth/password-recovery/reset", json={"reset_token": reset_token, "new_password": "anotherpassword"})
    assert response.status_code == 400
