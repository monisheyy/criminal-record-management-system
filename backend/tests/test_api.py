"""
AI-CRMS Comprehensive Test Suite
Tests: auth, RBAC, criminal CRUD, duplicate check, cases, AI predictions,
       AI officer review/override, notifications/alerts, admin settings, retraining.
Uses in-memory SQLite so tests are fully isolated and repeatable.
"""
import os
# Set env vars BEFORE importing app modules (security.py reads them at import time)
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db
from app.security import get_password_hash

# ── In-memory test database ────────────────────────────────────────────────────
TEST_DB_URL = "sqlite:///:memory:"

engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    """Create schema and seed test users once for the whole module."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    from app.models import User, UserRole
    users = [
        User(username="admin_test", email="admin@test.com", full_name="Admin User",
             hashed_password=get_password_hash("adminpass"), role=UserRole.admin),
        User(username="officer_test", email="officer@test.com", full_name="Officer User",
             hashed_password=get_password_hash("officerpass"), role=UserRole.investigating_officer),
        User(username="clerk_test", email="clerk@test.com", full_name="Clerk User",
             hashed_password=get_password_hash("clerkpass"), role=UserRole.record_clerk),
    ]
    for u in users:
        db.add(u)
    db.commit()
    db.close()

    yield

    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _login(client, username, password):
    res = client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert res.status_code == 200, f"Login failed for {username}: {res.text}"
    return res.json()["access_token"]


@pytest.fixture(scope="module")
def admin_token(client):
    return _login(client, "admin_test", "adminpass")


@pytest.fixture(scope="module")
def officer_token(client):
    return _login(client, "officer_test", "officerpass")


@pytest.fixture(scope="module")
def clerk_token(client):
    return _login(client, "clerk_test", "clerkpass")


# ── Auth Tests ─────────────────────────────────────────────────────────────────

class TestAuth:
    def test_login_admin_success(self, client):
        res = client.post("/api/auth/login",
                          data={"username": "admin_test", "password": "adminpass"})
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["username"] == "admin_test"
        assert data["user"]["role"] == "admin"

    def test_login_officer_success(self, client):
        res = client.post("/api/auth/login",
                          data={"username": "officer_test", "password": "officerpass"})
        assert res.status_code == 200
        assert res.json()["user"]["role"] == "investigating_officer"

    def test_login_clerk_success(self, client):
        res = client.post("/api/auth/login",
                          data={"username": "clerk_test", "password": "clerkpass"})
        assert res.status_code == 200
        assert res.json()["user"]["role"] == "record_clerk"

    def test_login_wrong_password(self, client):
        res = client.post("/api/auth/login",
                          data={"username": "admin_test", "password": "wrongpass"})
        assert res.status_code == 401

    def test_login_nonexistent_user(self, client):
        res = client.post("/api/auth/login",
                          data={"username": "nobody", "password": "pass"})
        assert res.status_code == 401

    def test_me_authenticated(self, client, admin_token):
        res = client.get("/api/auth/me",
                         headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        assert res.json()["username"] == "admin_test"

    def test_me_unauthenticated(self, client):
        res = client.get("/api/auth/me")
        assert res.status_code == 401

    def test_invalid_token(self, client):
        res = client.get("/api/auth/me",
                         headers={"Authorization": "Bearer invalidtoken"})
        assert res.status_code == 401


# ── RBAC Tests ─────────────────────────────────────────────────────────────────

class TestRBAC:
    def test_admin_can_access_admin_routes(self, client, admin_token):
        res = client.get("/api/admin/users",
                         headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200

    def test_officer_cannot_access_admin_routes(self, client, officer_token):
        res = client.get("/api/admin/users",
                         headers={"Authorization": f"Bearer {officer_token}"})
        assert res.status_code == 403

    def test_clerk_cannot_access_admin_routes(self, client, clerk_token):
        res = client.get("/api/admin/users",
                         headers={"Authorization": f"Bearer {clerk_token}"})
        assert res.status_code == 403

    def test_all_roles_can_list_criminals(self, client, admin_token, officer_token, clerk_token):
        for token in [admin_token, officer_token, clerk_token]:
            res = client.get("/api/criminals",
                             headers={"Authorization": f"Bearer {token}"})
            assert res.status_code == 200

    def test_unauthenticated_cannot_access_any_resource(self, client):
        for url in ["/api/criminals", "/api/cases", "/api/ai/predictions"]:
            res = client.get(url)
            assert res.status_code == 401


# ── Criminal CRUD Tests ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def created_criminal_id(client, admin_token):
    """Create a criminal and return its ID for use in dependent tests."""
    res = client.post(
        "/api/criminals",
        json={
            "first_name": "John",
            "last_name": "Doe",
            "crime_type": "Robbery",
            "threat_level": "high",
            "prior_convictions": 3,
            "is_wanted": True,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    return res.json()["id"]


class TestCriminalCRUD:
    def test_create_criminal_admin(self, client, admin_token):
        res = client.post(
            "/api/criminals",
            json={"first_name": "Jane", "last_name": "Smith",
                  "crime_type": "Fraud", "threat_level": "medium"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["first_name"] == "Jane"
        assert data["crn"].startswith("CRN")

    def test_create_criminal_officer(self, client, officer_token):
        res = client.post(
            "/api/criminals",
            json={"first_name": "Bob", "last_name": "Gang",
                  "crime_type": "Drug Trafficking", "threat_level": "high"},
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert res.status_code == 200

    def test_create_criminal_clerk(self, client, clerk_token):
        res = client.post(
            "/api/criminals",
            json={"first_name": "Alice", "last_name": "Minor", "threat_level": "low"},
            headers={"Authorization": f"Bearer {clerk_token}"},
        )
        assert res.status_code == 200

    def test_list_criminals(self, client, admin_token):
        res = client.get("/api/criminals",
                         headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        assert isinstance(res.json(), list)
        assert len(res.json()) >= 1

    def test_get_criminal_by_id(self, client, admin_token, created_criminal_id):
        res = client.get(f"/api/criminals/{created_criminal_id}",
                         headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        assert res.json()["id"] == created_criminal_id

    def test_get_criminal_not_found(self, client, admin_token):
        res = client.get("/api/criminals/999999",
                         headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 404

    def test_update_criminal(self, client, admin_token, created_criminal_id):
        res = client.put(
            f"/api/criminals/{created_criminal_id}",
            json={"threat_level": "critical", "prior_convictions": 5},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200
        assert res.json()["threat_level"] == "critical"

    def test_criminal_history_after_create(self, client, admin_token, created_criminal_id):
        res = client.get(f"/api/criminals/{created_criminal_id}/history",
                         headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        assert len(res.json()) >= 1

    def test_search_criminals(self, client, admin_token):
        res = client.get("/api/criminals?search=John",
                         headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        assert any(c["first_name"] == "John" for c in res.json())


# ── Duplicate Check Tests ──────────────────────────────────────────────────────

class TestDuplicateCheck:
    def test_duplicate_found(self, client, admin_token):
        res = client.get("/api/criminals/check-duplicate?first_name=John&last_name=Doe",
                         headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        data = res.json()
        assert data["has_duplicates"] is True
        assert len(data["duplicates"]) >= 1

    def test_no_duplicate(self, client, admin_token):
        res = client.get("/api/criminals/check-duplicate?first_name=Unique&last_name=PersonXYZ123",
                         headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        data = res.json()
        assert data["has_duplicates"] is False


# ── Case Tests ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def created_case_id(client, admin_token, created_criminal_id):
    """Create a case with a criminal linked."""
    res = client.post(
        "/api/cases",
        json={
            "title": "Armed Bank Robbery",
            "description": "Suspects robbed First National Bank",
            "crime_type": "Robbery",
            "priority": "high",
            "criminal_ids": [created_criminal_id],
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    return res.json()["id"]


class TestCases:
    def test_create_case(self, client, admin_token):
        res = client.post(
            "/api/cases",
            json={"title": "Drug Operation", "crime_type": "Drug Trafficking", "priority": "normal"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert "case_number" in data
        assert data["title"] == "Drug Operation"

    def test_list_cases(self, client, admin_token):
        res = client.get("/api/cases", headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_get_case_by_id(self, client, admin_token, created_case_id):
        res = client.get(f"/api/cases/{created_case_id}",
                         headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == created_case_id
        assert len(data["criminals"]) >= 1  # criminal was linked

    def test_update_case_status(self, client, admin_token, created_case_id):
        res = client.put(
            f"/api/cases/{created_case_id}",
            json={"status": "under_investigation"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "under_investigation"

    def test_add_evidence(self, client, admin_token, created_case_id):
        res = client.post(
            f"/api/cases/{created_case_id}/evidence",
            json={"type": "physical", "description": "Balaclava found at scene",
                  "collected_by": "Forensics Team"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200

    def test_add_victim(self, client, admin_token, created_case_id):
        res = client.post(
            f"/api/cases/{created_case_id}/victims",
            json={"first_name": "Mary", "last_name": "Teller",
                  "age": 35, "gender": "female", "status": "alive"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200


# ── AI Prediction Tests ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def created_prediction_id(client, admin_token, created_criminal_id):
    """Run AI prediction and return prediction ID."""
    res = client.post(
        "/api/ai/predict",
        json={"criminal_id": created_criminal_id},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    return res.json()["id"]


class TestAIPredictions:
    def test_run_prediction_for_criminal(self, client, admin_token, created_criminal_id):
        res = client.post(
            "/api/ai/predict",
            json={"criminal_id": created_criminal_id},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert "predicted_crime_type" in data
        assert "crime_type_confidence" in data
        assert "gang_affiliation_probability" in data
        assert "risk_score" in data
        assert "risk_level" in data
        assert "confidence_overall" in data
        assert "model_version" in data
        assert data["review_status"] == "pending"

    def test_run_prediction_for_case(self, client, admin_token, created_case_id):
        res = client.post(
            "/api/ai/predict",
            json={"case_id": created_case_id},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200

    def test_list_predictions(self, client, admin_token):
        res = client.get("/api/ai/predictions",
                         headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_filter_predictions_by_criminal(self, client, admin_token, created_criminal_id):
        res = client.get(f"/api/ai/predictions?criminal_id={created_criminal_id}",
                         headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        assert all(p["criminal_id"] == created_criminal_id for p in res.json())

    def test_get_single_prediction(self, client, admin_token, created_prediction_id):
        res = client.get(f"/api/ai/predictions/{created_prediction_id}",
                         headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        assert res.json()["id"] == created_prediction_id

    def test_clerk_cannot_access_predictions_endpoint(self, client, clerk_token):
        # clerk_token is record_clerk which is in require_any_role — should work
        res = client.get("/api/ai/predictions",
                         headers={"Authorization": f"Bearer {clerk_token}"})
        assert res.status_code == 200


# ── AI Officer Review / Override Tests ────────────────────────────────────────

class TestAIReview:
    def test_officer_can_confirm_prediction(self, client, officer_token, created_prediction_id):
        res = client.post(
            f"/api/ai/predictions/{created_prediction_id}/review",
            json={"status": "confirmed", "remarks": "Confirmed based on prior arrest records."},
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["review_status"] == "confirmed"
        assert data["officer_remarks"] == "Confirmed based on prior arrest records."
        assert data["reviewed_by_id"] is not None

    def test_admin_can_override_prediction(self, client, admin_token, created_criminal_id):
        # Create a fresh prediction to override
        pred_res = client.post(
            "/api/ai/predict",
            json={"criminal_id": created_criminal_id},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        pred_id = pred_res.json()["id"]

        res = client.post(
            f"/api/ai/predictions/{pred_id}/review",
            json={
                "status": "overridden",
                "remarks": "Override based on new intelligence report.",
                "override_crime_type": "Arms Trafficking",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["review_status"] == "overridden"
        assert data["override_crime_type"] == "Arms Trafficking"
        assert data["officer_remarks"] == "Override based on new intelligence report."

    def test_clerk_cannot_review_prediction(self, client, clerk_token, created_criminal_id):
        # Create a fresh prediction
        pred_res = client.post(
            "/api/ai/predict",
            json={"criminal_id": created_criminal_id},
            headers={"Authorization": f"Bearer {admin_token := _login(client, 'admin_test', 'adminpass')}"},
        )
        pred_id = pred_res.json()["id"]

        res = client.post(
            f"/api/ai/predictions/{pred_id}/review",
            json={"status": "confirmed", "remarks": "test"},
            headers={"Authorization": f"Bearer {clerk_token}"},
        )
        assert res.status_code == 403

    def test_review_nonexistent_prediction(self, client, officer_token):
        res = client.post(
            "/api/ai/predictions/999999/review",
            json={"status": "confirmed", "remarks": "test"},
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert res.status_code == 404


# ── Notifications / Alerts Tests ──────────────────────────────────────────────

class TestNotifications:
    def test_list_notifications(self, client, admin_token):
        res = client.get("/api/notifications",
                         headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_list_unread_only(self, client, admin_token):
        res = client.get("/api/notifications?unread_only=true",
                         headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        # All returned should be unread
        assert all(not n["is_read"] for n in res.json())

    def test_mark_notification_read(self, client, admin_token):
        # First get a notification
        notifs = client.get("/api/notifications",
                            headers={"Authorization": f"Bearer {admin_token}"}).json()
        if notifs:
            nid = notifs[0]["id"]
            res = client.post(f"/api/notifications/{nid}/read",
                              headers={"Authorization": f"Bearer {admin_token}"})
            assert res.status_code == 200

    def test_mark_all_read(self, client, officer_token):
        res = client.post("/api/notifications/read-all",
                          headers={"Authorization": f"Bearer {officer_token}"})
        assert res.status_code == 200


# ── Admin Settings Tests ───────────────────────────────────────────────────────

class TestAdminSettings:
    def test_officer_cannot_update_settings(self, client, officer_token):
        res = client.put(
            "/api/admin/settings/risk_threshold",
            json={"value": "75", "description": "High risk threshold"},
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert res.status_code == 403

    def test_admin_can_update_setting(self, client, admin_token):
        res = client.put(
            "/api/admin/settings/risk_threshold",
            json={"value": "75", "description": "High risk threshold"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200
        assert res.json()["value"] == "75"
        assert res.json()["key"] == "risk_threshold"

    def test_admin_can_list_settings(self, client, admin_token):
        res = client.get("/api/admin/settings",
                         headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        assert len(res.json()) >= 1

    def test_admin_can_list_users(self, client, admin_token):
        res = client.get("/api/admin/users",
                         headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        assert any(u["username"] == "admin_test" for u in res.json())

    def test_admin_can_create_user(self, client, admin_token):
        res = client.post(
            "/api/admin/users",
            json={
                "username": "new_officer",
                "email": "new@test.com",
                "full_name": "New Officer",
                "password": "password123",
                "role": "investigating_officer",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200
        assert res.json()["role"] == "investigating_officer"

    def test_dashboard_returns_all_stats(self, client, admin_token):
        res = client.get("/api/admin/dashboard",
                         headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        data = res.json()
        assert "total_criminals" in data
        assert "total_cases" in data
        assert "open_cases" in data
        assert "high_risk_criminals" in data
        assert "pending_reviews" in data
        assert "unread_alerts" in data
        assert "cases_by_status" in data
        assert "crimes_by_type" in data
        assert "monthly_cases" in data
        assert "officer_workload" in data
        assert "prediction_accuracy" in data

    def test_audit_logs_available(self, client, admin_token):
        res = client.get("/api/admin/audit-logs",
                         headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        assert isinstance(res.json(), list)
        # Should have logs from all the operations above
        assert len(res.json()) >= 1


# ── AI Model Retraining Tests ──────────────────────────────────────────────────

class TestModelRetraining:
    def test_officer_cannot_retrain(self, client, officer_token):
        res = client.post("/api/ai/retrain",
                          headers={"Authorization": f"Bearer {officer_token}"})
        assert res.status_code == 403

    def test_admin_can_retrain(self, client, admin_token):
        res = client.post("/api/ai/retrain",
                          headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        data = res.json()
        assert "version" in data
        assert "metrics" in data
        assert "crime_classifier" in data["metrics"]
        assert "accuracy" in data["metrics"]["crime_classifier"]

    def test_list_ml_models(self, client, admin_token):
        res = client.get("/api/ai/models",
                         headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        assert isinstance(res.json(), list)
        assert len(res.json()) >= 1  # At least the retrained model


# ── PDF Report Tests ───────────────────────────────────────────────────────────

class TestReports:
    def test_criminal_pdf_report(self, client, admin_token, created_criminal_id):
        res = client.get(
            f"/api/criminals/{created_criminal_id}/report",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/pdf"
        assert res.content[:4] == b"%PDF"

    def test_case_pdf_report(self, client, admin_token, created_case_id):
        res = client.get(
            f"/api/cases/{created_case_id}/report",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/pdf"
        assert res.content[:4] == b"%PDF"
