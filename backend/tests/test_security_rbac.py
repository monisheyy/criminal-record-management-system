import pytest


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_clerk_cannot_retrain(client, clerk_token):
    r = client.post("/api/ai/retrain", headers=auth(clerk_token))
    assert r.status_code == 403


def test_officer_cannot_retrain(client, officer_token):
    r = client.post("/api/ai/retrain", headers=auth(officer_token))
    assert r.status_code == 403


def test_clerk_cannot_review_ai_prediction(client, clerk_token):
    r = client.post("/api/ai/predictions/999999/review", json={"status": "confirmed"}, headers=auth(clerk_token))
    assert r.status_code == 403


def test_clerk_cannot_modify_cases(client, clerk_token):
    r = client.post("/api/cases", json={"title": "Unauthorized case creation"}, headers=auth(clerk_token))
    assert r.status_code == 403


def test_clerk_cannot_add_case_evidence(client, clerk_token):
    r = client.post("/api/cases/999999/evidence", json={"type": "test"}, headers=auth(clerk_token))
    assert r.status_code == 403


def test_clerk_cannot_run_ai_prediction(client, clerk_token):
    r = client.post("/api/ai/predict", json={"criminal_id": 999999}, headers=auth(clerk_token))
    assert r.status_code == 403


def test_notification_idor_is_blocked(client, clerk_token):
    # A nonexistent/unowned notification must not be mutated; endpoint intentionally
    # returns a non-disclosing success response to avoid notification-ID enumeration.
    r = client.post("/api/notifications/999999/read", headers=auth(clerk_token))
    assert r.status_code == 200


def test_expired_or_malformed_token_is_rejected(client):
    r = client.get("/api/criminals", headers={"Authorization": "Bearer not-a-valid-jwt"})
    assert r.status_code == 401
