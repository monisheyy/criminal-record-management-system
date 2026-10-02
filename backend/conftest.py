"""
conftest.py — sets required environment variables before any app module is imported.
This prevents the SECRET_KEY RuntimeError during test collection.
"""
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only-do-not-use-in-prod")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")



import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine, SessionLocal
from app.security import get_password_hash
from app.models import User, UserRole

@pytest.fixture(scope="session", autouse=True)
def setup_security_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    users = [("admin_test", "admin@test.com", "Admin User", "adminpass", UserRole.admin),
             ("officer_test", "officer@test.com", "Officer User", "officerpass", UserRole.investigating_officer),
             ("clerk_test", "clerk@test.com", "Clerk User", "clerkpass", UserRole.record_clerk)]
    for username, email, name, password, role in users:
        if not db.query(User).filter_by(username=username).first():
            db.add(User(username=username, email=email, full_name=name, hashed_password=get_password_hash(password), role=role))
    db.commit(); db.close()


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
    return r.json()["access_token"]

@pytest.fixture(scope="session")
def admin_token(client): return _login(client, "admin_test", "adminpass")
@pytest.fixture(scope="session")
def officer_token(client): return _login(client, "officer_test", "officerpass")
@pytest.fixture(scope="session")
def clerk_token(client): return _login(client, "clerk_test", "clerkpass")
