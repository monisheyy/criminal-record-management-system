from datetime import datetime, timedelta
import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import (
    verify_password, get_password_hash, create_access_token, get_current_user,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from app.utils.audit import create_audit_log
from app.utils.recovery import (
    generate_otp, generate_reset_token, hash_secret, secrets_match,
    get_recovery_provider, OTP_TTL_SECONDS, OTP_MAX_ATTEMPTS,
    REQUEST_COOLDOWN_SECONDS, REQUESTS_PER_IP_WINDOW, REQUESTS_PER_IP_MAX,
    RESET_TOKEN_TTL_SECONDS,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def utcnow() -> datetime:
    return datetime.utcnow()


def _find_user(db: Session, identifier: str):
    return db.query(models.User).filter(
        or_(models.User.username == identifier, models.User.email == identifier)
    ).first()


def _generic_recovery_response():
    return {"message": "If the account exists, a verification code has been issued."}


@router.post("/login", response_model=schemas.Token)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        create_audit_log(db, "USER_LOGIN_FAILED", username=form_data.username, resource_type="auth", status="failure", reason="Invalid credentials", ip_address=request.client.host if request and request.client else None)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password", headers={"WWW-Authenticate": "Bearer"})
    if not user.is_active:
        create_audit_log(db, "USER_LOGIN_FAILED", user_id=user.id, username=user.username, role=user.role, resource_type="auth", status="failure", reason="Inactive account", ip_address=request.client.host if request and request.client else None)
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = create_access_token(data={"sub": user.username}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    create_audit_log(db, "USER_LOGIN", user_id=user.id, username=user.username, role=user.role, resource_type="auth", ip_address=request.client.host if request and request.client else None)
    return schemas.Token(access_token=access_token, token_type="bearer", user=schemas.UserOut.model_validate(user))


@router.post("/password-recovery/request")
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
        destination = user.email
        get_recovery_provider().send_otp(destination, otp)
    except Exception:
        db.delete(challenge)
        db.commit()
        create_audit_log(db, "PASSWORD_RECOVERY_PROVIDER_FAILED", user_id=user.id, username=user.username, role=user.role, resource_type="auth", status="failure", reason="Recovery provider failure", ip_address=ip)
        raise HTTPException(status_code=503, detail="Password recovery service is temporarily unavailable")

    create_audit_log(db, "PASSWORD_RECOVERY_REQUESTED", user_id=user.id, username=user.username, role=user.role, resource_type="auth", status="success", reason="Verification challenge created", ip_address=ip)
    return _generic_recovery_response()


@router.post("/password-recovery/verify")
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

    if not challenge or challenge.otp_expires_at < now or challenge.attempts >= challenge.max_attempts:
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")

    if not secrets_match(payload.otp, challenge.otp_hash):
        challenge.attempts += 1
        if challenge.attempts >= challenge.max_attempts:
            challenge.consumed_at = now
        db.commit()
        create_audit_log(db, "PASSWORD_RECOVERY_OTP_FAILED", user_id=user.id, username=user.username, role=user.role, resource_type="auth", status="failure", reason="Invalid verification code", ip_address=ip)
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")

    reset_token = generate_reset_token()
    challenge.reset_token_hash = hash_secret(reset_token)
    challenge.reset_token_expires_at = now + timedelta(seconds=RESET_TOKEN_TTL_SECONDS)
    challenge.verified_at = now
    challenge.consumed_at = now  # OTP is one-time; reset token is the separate credential.
    db.commit()
    create_audit_log(db, "PASSWORD_RECOVERY_OTP_VERIFIED", user_id=user.id, username=user.username, role=user.role, resource_type="auth", status="success", reason="OTP verified", ip_address=ip)
    return {"reset_token": reset_token, "expires_in": RESET_TOKEN_TTL_SECONDS}


@router.post("/password-recovery/reset")
async def password_recovery_reset(request: Request, payload: schemas.PasswordReset, db: Session = Depends(get_db)):
    now = utcnow()
    ip = request.client.host if request.client else None
    token_hash = hash_secret(payload.reset_token)
    candidates = db.query(models.PasswordRecovery).filter(
        models.PasswordRecovery.reset_token_hash == token_hash,
        models.PasswordRecovery.reset_consumed_at.is_(None),
    ).order_by(models.PasswordRecovery.id.desc()).all()
    matched = candidates[0] if candidates else None
    if not matched or not matched.reset_token_expires_at or matched.reset_token_expires_at < now:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user = db.query(models.User).filter(models.User.id == matched.user_id, models.User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user.hashed_password = get_password_hash(payload.new_password)
    matched.reset_consumed_at = now
    matched.reset_token_hash = None
    matched.reset_token_expires_at = None
    db.commit()
    create_audit_log(db, "PASSWORD_RESET_COMPLETED", user_id=user.id, username=user.username, role=user.role, resource_type="auth", status="success", reason="Password reset completed", ip_address=ip)
    return {"message": "Password reset successful. Please sign in with your new password."}


@router.get("/me", response_model=schemas.UserOut)
async def get_me(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.post("/logout")
async def logout(request: Request, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    create_audit_log(db, "USER_LOGOUT", user_id=current_user.id, username=current_user.username, role=current_user.role, resource_type="auth", ip_address=request.client.host if request.client else None)
    return {"message": "Logged out"}
