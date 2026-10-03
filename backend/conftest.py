"""
conftest.py — configures an isolated test environment before any app module is imported.

* In-memory database, created through the real Alembic migrations (so every
  test run also checks that the migrations produce a working schema).
* ML artifacts are written to a throw-away directory: tests can never
  overwrite the developer's active model in app/ml/saved_models.
* Demo seeding is off and auth rate limits are relaxed; dedicated tests
  tighten them explicitly.
"""
import os
import tempfile

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only-do-not-use-in-prod")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SEED_DEMO_DATA", "false")
os.environ.setdefault("RATE_LIMIT_AUTH_PER_MINUTE", "10000")
os.environ.setdefault("LOGIN_MAX_FAILED_ATTEMPTS", "5")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("AI_CRMS_MODEL_DIR", tempfile.mkdtemp(prefix="ai_crms_test_models_"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app.db_bootstrap import migrate_database  # noqa: E402
from app.security import get_password_hash  # noqa: E402
from app.models import User, UserRole  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def setup_security_db():
    migrate_database(engine, allow_auto_upgrade=True)
    db = SessionLocal()
    users = [("admin_test", "admin@test.com", "Admin User", "adminpass", UserRole.admin),
             ("officer_test", "officer@test.com", "Officer User", "officerpass", UserRole.investigating_officer),
             ("clerk_test", "clerk@test.com", "Clerk User", "clerkpass", UserRole.record_clerk)]
    for username, email, name, password, role in users:
        if not db.query(User).filter_by(username=username).first():
            db.add(User(username=username, email=email, full_name=name, hashed_password=get_password_hash(password), role=role))
    db.commit()
    db.close()


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


@pytest.fixture
def db(db_session):
    return db_session


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def _login(client, username, password):
    r = client.post("/api/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    # Tests authenticate with explicit Bearer headers; drop the session cookie so
    # one test's login never silently authenticates another test's requests.
    client.cookies.clear()
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin_token(client): return _login(client, "admin_test", "adminpass")
@pytest.fixture(scope="session")
def officer_token(client): return _login(client, "officer_test", "officerpass")
@pytest.fixture(scope="session")
def clerk_token(client): return _login(client, "clerk_test", "clerkpass")
