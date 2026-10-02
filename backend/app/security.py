from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
import bcrypt
import os
from dotenv import load_dotenv

load_dotenv()

_SECRET_KEY = os.getenv("SECRET_KEY")
if not _SECRET_KEY:
    raise RuntimeError("SECRET_KEY is not set. Please add it to your .env file.")
if len(_SECRET_KEY) < 32:
    raise RuntimeError("SECRET_KEY must be at least 32 characters long")
SECRET_KEY = _SECRET_KEY
ALGORITHM = os.getenv("ALGORITHM", "HS256")
if ALGORITHM not in {"HS256"}:
    raise RuntimeError("Unsupported JWT algorithm; only HS256 is allowed")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))
if not 5 <= ACCESS_TOKEN_EXPIRE_MINUTES <= 1440:
    raise RuntimeError("ACCESS_TOKEN_EXPIRE_MINUTES must be between 5 and 1440")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def get_password_hash(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password must contain at least 8 characters")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": now, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username or payload.get("type") != "access":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None or not user.is_active:
        raise credentials_exception
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
