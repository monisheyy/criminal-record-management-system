"""Authentication, session and role-based authorization primitives.

Sessions
--------
* Browser clients authenticate with an HttpOnly, SameSite cookie that page
  JavaScript cannot read (mitigates token theft through XSS). Unsafe methods
  authenticated by cookie must also send ``X-Requested-With`` – a header a
  cross-site form cannot set and CORS only allows from allow-listed origins –
  which provides CSRF protection.
* API clients (scripts, tests) may still send ``Authorization: Bearer``.

Every token carries a unique ``jti`` (individually revocable on logout) and
the user's ``token_version`` (incremented to invalidate *all* of a user's
sessions after a password change/reset, deactivation or role change).
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
import uuid

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from jwt import PyJWTError as JWTError
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.database import get_db

SECRET_KEY = settings.secret_key
ALGORITHM = settings.algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes

SESSION_COOKIE_NAME = "acrms_session"
CSRF_HEADER = "X-Requested-With"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Endpoints a user who must change their password may still call.
PASSWORD_CHANGE_ALLOWED_PATHS = {"/api/auth/me", "/api/auth/change-password", "/api/auth/logout"}

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """SQLite returns naive datetimes; treat them as UTC for comparisons."""
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# Known-compromised / demo passwords that must never be (re)used. Following
# NIST SP 800-63B, the policy favours length and blocklisting over arbitrary
# composition rules.
BLOCKED_PASSWORDS = {
    "admin123", "officer123", "clerk123", "password", "password1", "password123",
    "12345678", "123456789", "1234567890", "qwerty123", "letmein123", "welcome123",
    "changeme", "changeme123", "iloveyou", "administrator", "p@ssw0rd", "passw0rd",
}
PASSWORD_POLICY_MIN_LENGTH = 10


def validate_password_strength(password: str, *, username: Optional[str] = None) -> None:
    """Raise ValueError when a new password does not meet the policy."""
    if not PASSWORD_POLICY_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        raise ValueError(f"Password must be {PASSWORD_POLICY_MIN_LENGTH}-{PASSWORD_MAX_LENGTH} characters long")
    if password.lower() in BLOCKED_PASSWORDS:
        raise ValueError("This password is too common or has been published; choose another")
    if len(set(password)) < 4:
        raise ValueError("Password is too repetitive")
    if username and len(username) >= 3 and username.lower() in password.lower():
        raise ValueError("Password must not contain the username")


def get_password_hash(password: str) -> str:
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must contain at least {PASSWORD_MIN_LENGTH} characters")
    # bcrypt only uses the first 72 bytes; reject longer inputs instead of truncating silently.
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password is too long (bcrypt limit is 72 bytes)")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_access_token(user: models.User, expires_delta: Optional[timedelta] = None) -> Tuple[str, datetime]:
    now = utcnow()
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    claims = {
        "sub": user.username,
        "uid": user.id,
        "ver": user.token_version or 0,
        "jti": uuid.uuid4().hex,
        "type": "access",
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(claims, SECRET_KEY, algorithm=ALGORITHM), expire


def decode_token(token: str) -> dict:
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    if payload.get("type") != "access" or not payload.get("sub") or not payload.get("jti"):
        raise JWTError("Malformed token")
    return payload


def resolve_token_user(db: Session, token: str) -> Tuple[models.User, dict]:
    """Validate a raw token and return its active user. Raises JWTError."""
    payload = decode_token(token)
    if db.get(models.RevokedToken, payload["jti"]) is not None:
        raise JWTError("Token revoked")
    user = db.query(models.User).filter(models.User.username == payload["sub"]).first()
    if user is None or not user.is_active:
        raise JWTError("Unknown or inactive user")
    if int(payload.get("ver", -1)) != int(user.token_version or 0):
        raise JWTError("Token version superseded")
    return user, payload


def revoke_token(db: Session, payload: dict, user_id: Optional[int]) -> None:
    jti = payload.get("jti")
    if not jti or db.get(models.RevokedToken, jti) is not None:
        return
    expires_at = datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc)
    db.add(models.RevokedToken(jti=jti, user_id=user_id, expires_at=expires_at))
    # Opportunistically purge entries that can no longer be replayed.
    db.query(models.RevokedToken).filter(models.RevokedToken.expires_at < utcnow()).delete(synchronize_session=False)


def invalidate_all_sessions(user: models.User) -> None:
    user.token_version = (user.token_version or 0) + 1


def _extract_token(request: Request, bearer: Optional[str]) -> Tuple[Optional[str], bool]:
    if bearer:
        return bearer, False
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    return (cookie, True) if cookie else (None, False)


async def get_current_user(
    request: Request,
    bearer: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token, from_cookie = _extract_token(request, bearer)
    if not token:
        raise credentials_exception
    if from_cookie and request.method in UNSAFE_METHODS and not request.headers.get(CSRF_HEADER):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF check failed")
    try:
        user, payload = resolve_token_user(db, token)
    except JWTError:
        raise credentials_exception

    if user.must_change_password and request.url.path not in PASSWORD_CHANGE_ALLOWED_PATHS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password change required before continuing",
            headers={"X-Password-Change-Required": "true"},
        )
    request.state.token_payload = payload
    return user


def require_roles(*roles: str):
    async def role_checker(current_user: models.User = Depends(get_current_user)):
        if current_user.role.value not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user
    return role_checker


require_admin = require_roles("admin")
require_officer_or_admin = require_roles("admin", "investigating_officer")
require_clerk_or_officer_or_admin = require_roles("admin", "investigating_officer", "record_clerk")
require_any_role = require_roles("admin", "investigating_officer", "record_clerk")


def officer_can_access_case(user: models.User, case: models.Case) -> bool:
    """Object-level rule shared by all case-scoped endpoints.

    Admins and record clerks have organisation-wide access. Investigating
    officers may access cases assigned to them and unassigned cases (so they
    can pick them up), but not cases assigned to another officer.
    """
    if user.role.value != "investigating_officer":
        return True
    return case.assigned_officer_id in (None, user.id)


def ensure_case_access(user: models.User, case: models.Case) -> None:
    if not officer_can_access_case(user, case):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not assigned to this case")
