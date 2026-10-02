from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from jwt import PyJWTError as JWTError
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app import models, schemas
from app.security import (
    SESSION_COOKIE_NAME, ACCESS_TOKEN_EXPIRE_MINUTES,
    as_utc, create_access_token, get_current_user, get_password_hash,
    invalidate_all_sessions, oauth2_scheme, resolve_token_user, revoke_token,
    utcnow, validate_password_strength, verify_password,
)
from app.utils.audit import create_audit_log
from app.utils.rate_limit import rate_limit
from app.utils.recovery import (
    generate_otp, generate_reset_token, hash_secret, secrets_match,
    get_recovery_provider, OTP_TTL_SECONDS, OTP_MAX_ATTEMPTS,
    REQUEST_COOLDOWN_SECONDS, REQUESTS_PER_IP_WINDOW, REQUESTS_PER_IP_MAX,
    RESET_TOKEN_TTL_SECONDS,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

GENERIC_LOGIN_ERROR = "Incorrect username or password, or the account is temporarily locked."
# A valid bcrypt hash used to equalise response time for unknown usernames.
_DUMMY_HASH = get_password_hash("timing-equaliser-not-a-real-password")


def _find_user(db: Session, identifier: str):
    return db.query(models.User).filter(
        or_(models.User.username == identifier, models.User.email == identifier)
    ).first()


def _generic_recovery_response():
    return {"message": "If the account exists, a verification code has been issued."}


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME, path="/", httponly=True,
        secure=settings.cookie_secure, samesite=settings.cookie_samesite,
    )


def _issue_session(response: Response, user: models.User) -> schemas.Token:
    token, expires_at = create_access_token(user, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    _set_session_cookie(response, token)
    return schemas.Token(
        access_token=token,
        token_type="bearer",
        expires_at=expires_at,
        user=schemas.UserOut.model_validate(user),
    )


@router.post("/login", response_model=schemas.Token, dependencies=[Depends(rate_limit("login"))])
async def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    now = utcnow()
    user = db.query(models.User).filter(models.User.username == form_data.username).first()

    if user is None:
        verify_password(form_data.password, _DUMMY_HASH)  # constant-ish timing
        create_audit_log(db, "USER_LOGIN_FAILED", username=form_data.username[:50], resource_type="auth",
                         status="failure", reason="Unknown username")
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR, headers={"WWW-Authenticate": "Bearer"})

    locked_until = as_utc(user.locked_until)
    if locked_until and locked_until > now:
        verify_password(form_data.password, _DUMMY_HASH)
        create_audit_log(db, "USER_LOGIN_BLOCKED", actor=user, resource_type="auth", resource_id=user.id,
                         status="failure", reason="Account temporarily locked")
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR, headers={"WWW-Authenticate": "Bearer"})

    if not verify_password(form_data.password, user.hashed_password):
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        reason = "Invalid credentials"
        if user.failed_login_attempts >= settings.login_max_failed_attempts:
            user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
            user.failed_login_attempts = 0
            reason = f"Account locked for {settings.login_lockout_minutes} minutes after repeated failures"
        create_audit_log(db, "USER_LOGIN_FAILED", actor=user, resource_type="auth", resource_id=user.id,
                         status="failure", reason=reason, commit=False)
        db.commit()
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR, headers={"WWW-Authenticate": "Bearer"})

    if not user.is_active:
        create_audit_log(db, "USER_LOGIN_FAILED", actor=user, resource_type="auth", resource_id=user.id,
                         status="failure", reason="Inactive account")
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR, headers={"WWW-Authenticate": "Bearer"})

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    create_audit_log(db, "USER_LOGIN", actor=user, resource_type="auth", resource_id=user.id,
                     details={"must_change_password": bool(user.must_change_password)}, commit=False)
    db.commit()
    db.refresh(user)
    return _issue_session(response, user)


@router.post("/change-password", response_model=schemas.Token)
async def change_password(
    payload: schemas.PasswordChange,
    request: Request,
    response: Response,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.current_password, current_user.hashed_password):
        create_audit_log(db, "PASSWORD_CHANGE_FAILED", actor=current_user, resource_type="auth",
                         resource_id=current_user.id, status="failure", reason="Current password incorrect")
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="New password must differ from the current password")
    try:
        validate_password_strength(payload.new_password, username=current_user.username)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    current_user.hashed_password = get_password_hash(payload.new_password)
    current_user.must_change_password = False
    current_user.password_changed_at = utcnow()
    invalidate_all_sessions(current_user)  # other devices/sessions are signed out
    create_audit_log(db, "PASSWORD_CHANGED", actor=current_user, resource_type="auth",
                     resource_id=current_user.id, reason="User changed own password", commit=False)
    db.commit()
    db.refresh(current_user)
    return _issue_session(response, current_user)


@router.post("/password-recovery/request", dependencies=[Depends(rate_limit("recovery"))])
async def password_recovery_request(request: Request, payload: schemas.PasswordRecoveryRequest, db: Session = Depends(get_db)):
    now = utcnow()
    ip = request.client.host if request.client else None
    user = _find_user(db, payload.identifier.strip())

    # IP-level throttle protects the endpoint even for nonexistent accounts.
    if ip:
        recent_ip = db.query(models.PasswordRecovery).filter(
            models.PasswordRecovery.request_ip == ip,
            models.PasswordRecovery.created_at >= now - timedelta(seconds=REQUESTS_PER_IP_WINDOW),
        ).count()
        if recent_ip >= REQUESTS_PER_IP_MAX:
            return _generic_recovery_response()

    if not user or not user.is_active:
        return _generic_recovery_response()

    recent = db.query(models.PasswordRecovery).filter(
        models.PasswordRecovery.user_id == user.id,
        models.PasswordRecovery.created_at >= now - timedelta(seconds=REQUEST_COOLDOWN_SECONDS),
        models.PasswordRecovery.consumed_at.is_(None),
    ).first()
    if recent:
        return _generic_recovery_response()

    # Invalidate all previous outstanding recovery attempts for this account.
    db.query(models.PasswordRecovery).filter(
        models.PasswordRecovery.user_id == user.id,
        models.PasswordRecovery.consumed_at.is_(None),
    ).update({models.PasswordRecovery.consumed_at: now}, synchronize_session=False)

    otp = generate_otp()
    challenge = models.PasswordRecovery(
        user_id=user.id,
        request_ip=ip,
        otp_hash=hash_secret(otp),
        otp_expires_at=now + timedelta(seconds=OTP_TTL_SECONDS),
        attempts=0,
        max_attempts=OTP_MAX_ATTEMPTS,
    )
    db.add(challenge)
    db.commit()

    try:
        get_recovery_provider().send_otp(user.email, otp)
    except Exception:
        db.delete(challenge)
        db.commit()
        create_audit_log(db, "PASSWORD_RECOVERY_PROVIDER_FAILED", actor=user, resource_type="auth", status="failure", reason="Recovery provider failure", ip_address=ip)
        raise HTTPException(status_code=503, detail="Password recovery service is temporarily unavailable")

    create_audit_log(db, "PASSWORD_RECOVERY_REQUESTED", actor=user, resource_type="auth", status="success", reason="Verification challenge created", ip_address=ip)
    return _generic_recovery_response()


@router.post("/password-recovery/verify", dependencies=[Depends(rate_limit("recovery"))])
async def password_recovery_verify(request: Request, payload: schemas.PasswordRecoveryVerify, db: Session = Depends(get_db)):
    now = utcnow()
    ip = request.client.host if request.client else None
    user = _find_user(db, payload.identifier.strip())
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")

    challenge = db.query(models.PasswordRecovery).filter(
        models.PasswordRecovery.user_id == user.id,
        models.PasswordRecovery.consumed_at.is_(None),
    ).order_by(models.PasswordRecovery.id.desc()).first()

    if not challenge or as_utc(challenge.otp_expires_at) < now or challenge.attempts >= challenge.max_attempts:
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")

    if not secrets_match(payload.otp, challenge.otp_hash):
        challenge.attempts += 1
        if challenge.attempts >= challenge.max_attempts:
            challenge.consumed_at = now
        db.commit()
        create_audit_log(db, "PASSWORD_RECOVERY_OTP_FAILED", actor=user, resource_type="auth", status="failure", reason="Invalid verification code", ip_address=ip)
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")

    reset_token = generate_reset_token()
    challenge.reset_token_hash = hash_secret(reset_token)
    challenge.reset_token_expires_at = now + timedelta(seconds=RESET_TOKEN_TTL_SECONDS)
    challenge.verified_at = now
    challenge.consumed_at = now  # OTP is one-time; reset token is the separate credential.
    db.commit()
    create_audit_log(db, "PASSWORD_RECOVERY_OTP_VERIFIED", actor=user, resource_type="auth", status="success", reason="OTP verified", ip_address=ip)
    return {"reset_token": reset_token, "expires_in": RESET_TOKEN_TTL_SECONDS}


@router.post("/password-recovery/reset", dependencies=[Depends(rate_limit("recovery"))])
async def password_recovery_reset(request: Request, payload: schemas.PasswordReset, db: Session = Depends(get_db)):
    now = utcnow()
    ip = request.client.host if request.client else None
    token_hash = hash_secret(payload.reset_token)
    matched = db.query(models.PasswordRecovery).filter(
        models.PasswordRecovery.reset_token_hash == token_hash,
        models.PasswordRecovery.reset_consumed_at.is_(None),
    ).order_by(models.PasswordRecovery.id.desc()).first()
    if not matched or not matched.reset_token_expires_at or as_utc(matched.reset_token_expires_at) < now:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user = db.query(models.User).filter(models.User.id == matched.user_id, models.User.is_active.is_(True)).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    try:
        validate_password_strength(payload.new_password, username=user.username)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    user.hashed_password = get_password_hash(payload.new_password)
    user.must_change_password = False
    user.password_changed_at = now
    user.failed_login_attempts = 0
    user.locked_until = None
    invalidate_all_sessions(user)  # any stolen session is cut off by a reset
    matched.reset_consumed_at = now
    matched.reset_token_hash = None
    matched.reset_token_expires_at = None
    create_audit_log(db, "PASSWORD_RESET_COMPLETED", actor=user, resource_type="auth", status="success",
                     reason="Password reset completed; all sessions invalidated", ip_address=ip, commit=False)
    db.commit()
    return {"message": "Password reset successful. Please sign in with your new password."}


@router.get("/me", response_model=schemas.UserOut)
async def get_me(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    bearer: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    """Revoke the presented token (if still valid) and always clear the cookie.

    Logout deliberately does not require a valid session: page JavaScript
    cannot delete the HttpOnly cookie, so the server must always clear it.
    """
    token = bearer or request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        try:
            user, payload = resolve_token_user(db, token)
        except JWTError:
            user = None
        if user is not None:
            revoke_token(db, payload, user.id)
            create_audit_log(db, "USER_LOGOUT", actor=user, resource_type="auth", commit=False)
            db.commit()
    _clear_session_cookie(response)
    return {"message": "Logged out"}
