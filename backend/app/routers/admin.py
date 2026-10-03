from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import Response as RawResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.observability import metrics
from app.security import (
    get_password_hash, invalidate_all_sessions, require_admin, require_any_role,
    require_officer_or_admin, validate_password_strength,
)
from app.utils.audit import create_audit_log, verify_audit_log
from app.utils.pagination import like_term, paginate
from app.utils.reports import generate_analytics_excel, generate_analytics_report

router = APIRouter(prefix="/api/admin", tags=["admin"])
directory_router = APIRouter(prefix="/api/users", tags=["users"])


def _active_admin_count(db: Session, exclude_id: Optional[int] = None) -> int:
    q = db.query(models.User).filter(models.User.role == models.UserRole.admin, models.User.is_active.is_(True))
    if exclude_id is not None:
        q = q.filter(models.User.id != exclude_id)
    return q.count()


def _user_snapshot(user: models.User) -> dict:
    return {"email": user.email, "full_name": user.full_name, "role": user.role.value,
            "badge_number": user.badge_number, "department": user.department, "is_active": user.is_active,
            "must_change_password": user.must_change_password}


# ── Directory (officer pickers) ───────────────────────────────────────────────
@directory_router.get("/officers", response_model=List[schemas.UserSummary])
async def list_officers(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_officer_or_admin),
):
    """Active investigating officers (names/badges only) for case assignment."""
    return db.query(models.User).filter(
        models.User.role == models.UserRole.investigating_officer, models.User.is_active.is_(True)
    ).order_by(models.User.full_name).all()


# ── Users ────────────────────────────────────────────────────────────────────
@router.get("/users", response_model=List[schemas.UserOut])
async def list_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    return db.query(models.User).order_by(models.User.created_at.desc()).all()


@router.post("/users", response_model=schemas.UserOut)
async def create_user(
    data: schemas.UserCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    if db.query(models.User).filter(func.lower(models.User.username) == data.username.lower()).first():
        raise HTTPException(status_code=409, detail="Username already exists")
    if db.query(models.User).filter(func.lower(models.User.email) == str(data.email).lower()).first():
        raise HTTPException(status_code=409, detail="Email already exists")
    try:
        validate_password_strength(data.password, username=data.username)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    user = models.User(
        username=data.username,
        email=str(data.email),
        full_name=data.full_name,
        role=data.role,
        badge_number=data.badge_number,
        department=data.department,
        hashed_password=get_password_hash(data.password),
        # An administrator chose this password, so the user must replace it.
        must_change_password=True,
    )
    db.add(user)
    db.flush()
    create_audit_log(db, "USER_CREATED", actor=current_user, resource_type="user", resource_id=user.id,
                     details={"created_username": data.username, "role": data.role.value}, commit=False)
    db.commit()
    db.refresh(user)
    return user


@router.put("/users/{user_id}", response_model=schemas.UserOut)
async def update_user(
    user_id: int,
    data: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    update_data = data.model_dump(exclude_unset=True)
    unlock = update_data.pop("unlock", None)
    new_password = update_data.pop("password", None)

    demoting = "role" in update_data and update_data["role"] is not None and update_data["role"].value != "admin"
    deactivating = update_data.get("is_active") is False
    if user.id == current_user.id and (demoting or deactivating):
        raise HTTPException(status_code=409, detail="You cannot demote or deactivate your own account")
    if user.role == models.UserRole.admin and (demoting or deactivating) and _active_admin_count(db, exclude_id=user.id) == 0:
        raise HTTPException(status_code=409, detail="At least one active administrator must remain")
    if "email" in update_data and update_data["email"]:
        update_data["email"] = str(update_data["email"])
        clash = db.query(models.User).filter(func.lower(models.User.email) == update_data["email"].lower(),
                                             models.User.id != user.id).first()
        if clash:
            raise HTTPException(status_code=409, detail="Email already exists")

    before = _user_snapshot(user)
    role_changed = "role" in update_data and update_data["role"] is not None and update_data["role"] != user.role
    sessions_invalidated = False

    if new_password:
        try:
            validate_password_strength(new_password, username=user.username)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        user.hashed_password = get_password_hash(new_password)
        user.password_changed_at = datetime.now(timezone.utc)
        update_data.setdefault("must_change_password", True)
        sessions_invalidated = True
    for k, v in update_data.items():
        setattr(user, k, v)
    if unlock:
        user.locked_until = None
        user.failed_login_attempts = 0
    if role_changed or deactivating:
        sessions_invalidated = True
    if sessions_invalidated:
        invalidate_all_sessions(user)

    after = _user_snapshot(user)
    create_audit_log(db, "ROLE_CHANGED" if role_changed else "USER_UPDATED", actor=current_user,
                     resource_type="user", resource_id=user_id, reason="Administrative user update",
                     details={"before": before, "after": after, "role_change": role_changed,
                              "password_reset_by_admin": bool(new_password), "unlocked": bool(unlock),
                              "sessions_invalidated": sessions_invalidated},
                     commit=False)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == models.UserRole.admin and _active_admin_count(db, exclude_id=user.id) == 0:
        raise HTTPException(status_code=409, detail="At least one active administrator must remain")
    referenced = any([
        db.query(models.AuditLog.id).filter(models.AuditLog.user_id == user_id).first(),
        db.query(models.Case.id).filter(or_(models.Case.assigned_officer_id == user_id,
                                            models.Case.created_by_id == user_id)).first(),
        db.query(models.AIPrediction.id).filter(models.AIPrediction.reviewed_by_id == user_id).first(),
        db.query(models.Criminal.id).filter(models.Criminal.created_by_id == user_id).first(),
    ])
    if referenced:
        raise HTTPException(
            status_code=409,
            detail="This account is referenced by records and audit history. Deactivate it instead of deleting it.",
        )
    snapshot = {"username": user.username, "role": user.role.value}
    db.query(models.NotificationRead).filter(models.NotificationRead.user_id == user_id).delete(synchronize_session=False)
    db.query(models.RevokedToken).filter(models.RevokedToken.user_id == user_id).delete(synchronize_session=False)
    db.query(models.PasswordRecovery).filter(models.PasswordRecovery.user_id == user_id).delete(synchronize_session=False)
    db.delete(user)
    create_audit_log(db, "USER_DELETED", actor=current_user, resource_type="user", resource_id=user_id,
                     details=snapshot, commit=False)
    db.commit()
    return {"message": "User deleted"}


# ── Audit Logs ───────────────────────────────────────────────────────────────
def _parse_date(value: Optional[str], name: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{name} must be an ISO-8601 date or datetime")
    return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed


@router.get("/audit-logs", response_model=List[schemas.AuditLogOut])
async def list_audit_logs(
    response: Response,
    action: Optional[str] = Query(None, max_length=100),
    resource_type: Optional[str] = Query(None, max_length=50),
    user_id: Optional[int] = Query(None, ge=1),
    status: Optional[str] = Query(None, max_length=20),
    request_id: Optional[str] = Query(None, max_length=64),
    date_from: Optional[str] = Query(None, max_length=40),
    date_to: Optional[str] = Query(None, max_length=40),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    q = db.query(models.AuditLog)
    if action:
        q = q.filter(models.AuditLog.action.ilike(like_term(action), escape="\\"))
    if resource_type:
        q = q.filter(models.AuditLog.resource_type == resource_type)
    if user_id:
        q = q.filter(models.AuditLog.user_id == user_id)
    if status:
        q = q.filter(models.AuditLog.status == status)
    if request_id:
        q = q.filter(models.AuditLog.request_id == request_id)
    start, end = _parse_date(date_from, "date_from"), _parse_date(date_to, "date_to")
    if start:
        q = q.filter(models.AuditLog.created_at >= start)
    if end:
        q = q.filter(models.AuditLog.created_at < end)
    q = q.order_by(models.AuditLog.created_at.desc(), models.AuditLog.id.desc())
    return paginate(q, response, skip, limit)


@router.get("/audit-logs/verify")
async def verify_audit_logs(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Recompute entry HMACs to detect modified audit records."""
    result = verify_audit_log(db)
    create_audit_log(db, "AUDIT_LOG_VERIFIED", actor=current_user, resource_type="audit_log",
                     status="success" if result["intact"] else "failure",
                     details={"checked": result["checked"], "tampered_count": result["tampered_count"]})
    return result


# ── Operations ────────────────────────────────────────────────────────────────
@router.get("/metrics")
async def get_metrics(current_user: models.User = Depends(require_admin)):
    """Per-process request counts, error counts and latency by route."""
    return metrics.snapshot()


# ── Dashboard Stats ───────────────────────────────────────────────────────────
def _build_dashboard_analytics(db: Session, user: models.User) -> dict:
    total_criminals = db.query(models.Criminal).count()
    total_cases = db.query(models.Case).count()
    open_cases = db.query(models.Case).filter(models.Case.status == models.CaseStatus.open).count()
    high_risk = db.query(models.Criminal).filter(models.Criminal.risk_score >= 75).count()
    pending_reviews = db.query(models.AIPrediction).filter(
        models.AIPrediction.review_status == models.PredictionStatus.pending).count()
    from app.routers.notifications import _read_by_user, _visible_filter
    unread_alerts = db.query(models.Notification.id).filter(
        _visible_filter(user), ~_read_by_user(user), models.Notification.notification_type == "alert").count()
    status_counts = db.query(models.Case.status, func.count(models.Case.id)).group_by(models.Case.status).all()
    crime_counts = db.query(models.Criminal.crime_type, func.count(models.Criminal.id)).filter(
        models.Criminal.crime_type.isnot(None)).group_by(models.Criminal.crime_type).all()

    # Calendar months (UTC), oldest first.
    now = datetime.now(timezone.utc)
    month_starts = []
    year, month = now.year, now.month
    for _ in range(6):
        month_starts.append(datetime(year, month, 1))
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    month_starts.reverse()
    monthly = []
    for index, start in enumerate(month_starts):
        end = month_starts[index + 1] if index + 1 < len(month_starts) else (
            datetime(start.year + 1, 1, 1) if start.month == 12 else datetime(start.year, start.month + 1, 1))
        count = db.query(models.Case).filter(models.Case.created_at >= start, models.Case.created_at < end).count()
        monthly.append({"month": start.strftime("%b %Y"), "cases": count})

    workload = db.query(models.User.full_name, func.count(models.Case.id).label('cases')).join(
        models.Case, (models.Case.assigned_officer_id == models.User.id)
        & (models.Case.status.in_([models.CaseStatus.open, models.CaseStatus.under_investigation])),
        isouter=True,
    ).filter(models.User.role == models.UserRole.investigating_officer,
             models.User.is_active.is_(True)).group_by(models.User.id, models.User.full_name).all()

    total_reviewed = db.query(models.AIPrediction).filter(
        models.AIPrediction.review_status != models.PredictionStatus.pending).count()
    confirmed = db.query(models.AIPrediction).filter(
        models.AIPrediction.review_status == models.PredictionStatus.confirmed).count()
    agreement = round((confirmed / total_reviewed * 100) if total_reviewed else 0.0, 1)
    return {
        "total_criminals": total_criminals, "total_cases": total_cases, "open_cases": open_cases,
        "high_risk_criminals": high_risk, "pending_reviews": pending_reviews, "unread_alerts": unread_alerts,
        "cases_by_status": {s.value: c for s, c in status_counts},
        "crimes_by_type": {ct: c for ct, c in crime_counts if ct},
        "monthly_cases": monthly,
        "officer_workload": [{"officer": name, "cases": count} for name, count in workload],
        "prediction_accuracy": agreement,
        "reviewer_agreement_rate": agreement,
        "reviewed_predictions": total_reviewed,
    }


@router.get("/dashboard", response_model=schemas.DashboardStats)
async def get_dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    return schemas.DashboardStats(**_build_dashboard_analytics(db, current_user))


@router.get("/dashboard/report/excel")
async def export_dashboard_excel(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    content = generate_analytics_excel(_build_dashboard_analytics(db, current_user))
    create_audit_log(db, "ANALYTICS_REPORT_EXCEL_GENERATED", actor=current_user, resource_type="dashboard")
    return RawResponse(content=content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       headers={"Content-Disposition": 'attachment; filename="ai_crms_dashboard_analytics.xlsx"'})


@router.get("/dashboard/report/pdf")
async def export_dashboard_pdf(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    content = generate_analytics_report(_build_dashboard_analytics(db, current_user))
    create_audit_log(db, "ANALYTICS_REPORT_PDF_GENERATED", actor=current_user, resource_type="dashboard")
    return RawResponse(content=content, media_type="application/pdf",
                       headers={"Content-Disposition": 'attachment; filename="ai_crms_dashboard_analytics.pdf"'})


# ── System Settings ───────────────────────────────────────────────────────────
@router.get("/settings", response_model=List[schemas.SystemSettingOut])
async def list_settings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    return db.query(models.SystemSetting).all()


@router.put("/settings/{key}", response_model=schemas.SystemSettingOut)
async def update_setting(
    key: str,
    data: schemas.SystemSettingUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    if not (1 <= len(key) <= 50) or not key.replace("_", "").replace(".", "").isalnum():
        raise HTTPException(status_code=422, detail="Setting key must be 1-50 characters: letters, digits, '_' or '.'")
    setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
    previous = setting.value if setting else None
    if not setting:
        setting = models.SystemSetting(key=key, value=data.value, description=data.description)
        db.add(setting)
    else:
        setting.value = data.value
        if data.description is not None:
            setting.description = data.description
    setting.updated_by_id = current_user.id
    create_audit_log(db, "SETTING_UPDATED", actor=current_user, resource_type="system_setting",
                     details={"key": key, "previous_value": previous, "value": data.value}, commit=False)
    db.commit()
    db.refresh(setting)
    return setting
