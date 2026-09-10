"""
conftest.py — sets required environment variables before any app module is imported.
This prevents the SECRET_KEY RuntimeError during test collection.
"""
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only-do-not-use-in-prod")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
