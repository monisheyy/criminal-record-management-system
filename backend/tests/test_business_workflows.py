"""High-value API business workflow tests for AI-CRMS.

These tests intentionally exercise persisted entities and authorization boundaries,
not merely application startup or HTTP status codes.
"""
from datetime import datetime, timedelta, timezone
from jose import jwt

from app import models
from app.security import SECRET_KEY, ALGORITHM


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def make_criminal(client, token, first="QA", last="Criminal"):
    r = client.post("/api/criminals", json={
        "first_name": first, "last_name": last,
        "crime_type": "Robbery", "crime_category": "violent",
        "prior_convictions": 2, "is_wanted": True,
    }, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def make_case(client, token, title="QA Case"):
    r = client.post("/api/cases", json={
        "title": title, "crime_type": "Robbery", "crime_category": "violent",
        "location": "QA Location",
    }, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def test_expired_access_token_is_rejected(client):
    now = datetime.now(timezone.utc)
    token = jwt.encode({"sub": "admin_test", "type": "access", "iat": now - timedelta(hours=2), "exp": now - timedelta(minutes=1)}, SECRET_KEY, algorithm=ALGORITHM)
    r = client.get("/api/auth/me", headers=auth(token))
    assert r.status_code == 401


def test_token_without_access_type_is_rejected(client):
    now = datetime.now(timezone.utc)
    token = jwt.encode({"sub": "admin_test", "iat": now, "exp": now + timedelta(minutes=5)}, SECRET_KEY, algorithm=ALGORITHM)
    r = client.get("/api/auth/me", headers=auth(token))
    assert r.status_code == 401


def test_criminal_crud_and_duplicate_search(client, admin_token):
    c = make_criminal(client, admin_token, "Duplicate", "Target")
    r = client.get("/api/criminals/check-duplicate", params={"first_name": "Duplicate", "last_name": "Target"}, headers=auth(admin_token))
    assert r.status_code == 200
    assert r.json()["has_duplicates"] is True

    r = client.put(f"/api/criminals/{c['id']}", json={"prior_convictions": 4}, headers=auth(admin_token))
    assert r.status_code == 200 and r.json()["prior_convictions"] == 4

    r = client.get("/api/criminals", params={"search": "Duplicate"}, headers=auth(admin_token))
    assert any(x["id"] == c["id"] for x in r.json())

    r = client.delete(f"/api/criminals/{c['id']}", headers=auth(admin_token))
    assert r.status_code == 200
    assert client.get(f"/api/criminals/{c['id']}", headers=auth(admin_token)).status_code == 404


def test_case_workflow_persists_relationships_and_reports(client, admin_token, officer_token):
    criminal = make_criminal(client, admin_token, "Case", "Subject")
    case = make_case(client, admin_token)

    r = client.post(f"/api/cases/{case['id']}/criminals", params={"criminal_id": criminal["id"], "role": "suspect"}, headers=auth(admin_token))
    assert r.status_code == 200

    r = client.post(f"/api/cases/{case['id']}/victims", json={"first_name":"Victim","last_name":"One","status":"alive"}, headers=auth(officer_token))
    assert r.status_code == 200

    r = client.post(f"/api/cases/{case['id']}/evidence", json={"type":"Digital","description":"QA evidence"}, headers=auth(officer_token))
    assert r.status_code == 200

    r = client.post(f"/api/cases/{case['id']}/assign", params={"officer_id": _user_id(client, "officer_test", admin_token)}, headers=auth(admin_token))
    assert r.status_code == 200

    detail = client.get(f"/api/cases/{case['id']}", headers=auth(officer_token))
    assert detail.status_code == 200
    assert len(detail.json()["criminals"]) == 1
    assert len(detail.json()["victims"]) == 1
    assert len(detail.json()["evidence"]) == 1

    for suffix, content_type in [("report", "application/pdf"), ("report/excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")]:
        r = client.get(f"/api/cases/{case['id']}/{suffix}", headers=auth(officer_token))
        assert r.status_code == 200
        assert r.headers["content-type"].startswith(content_type)


def _user_id(client, username, admin_token):
    users = client.get("/api/admin/users", headers=auth(admin_token))
    assert users.status_code == 200
    return next(u["id"] for u in users.json() if u["username"] == username)


def test_invalid_case_criminal_link_is_rejected(client, admin_token):
    case = make_case(client, admin_token, "Invalid Link Case")
    r = client.post(f"/api/cases/{case['id']}/criminals", params={"criminal_id": 999999}, headers=auth(admin_token))
    assert r.status_code == 404


def test_ai_prediction_persists_metrics_and_review(client, admin_token):
    criminal = make_criminal(client, admin_token, "AI", "Subject")
    r = client.post("/api/ai/predict", json={"criminal_id": criminal["id"]}, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    p = r.json()
    assert 0 <= p["crime_type_confidence"] <= 1
    assert 0 <= p["gang_affiliation_probability"] <= 1
    assert 0 <= p["risk_score"] <= 100
    assert p["id"]

    r2 = client.get(f"/api/ai/predictions/{p['id']}", headers=auth(admin_token))
    assert r2.status_code == 200
    assert r2.json()["id"] == p["id"]

    review = client.post(f"/api/ai/predictions/{p['id']}/review", json={"status":"overridden", "remarks":"QA override", "override_crime_type":"Fraud"}, headers=auth(admin_token))
    assert review.status_code == 200
    assert review.json()["review_status"] == "overridden"
    assert review.json()["override_crime_type"] == "Fraud"


def test_officer_cannot_assess_unrelated_criminal(client, admin_token, officer_token):
    criminal = make_criminal(client, admin_token, "Private", "Subject")
    r = client.post("/api/ai/predict", json={"criminal_id": criminal["id"]}, headers=auth(officer_token))
    assert r.status_code == 403


def test_notification_unread_count_and_acknowledgement(client, admin_token):
    before = client.get("/api/notifications", params={"unread_only": True}, headers=auth(admin_token))
    assert before.status_code == 200
    r = client.post("/api/notifications/999999/read", headers=auth(admin_token))
    assert r.status_code == 200
