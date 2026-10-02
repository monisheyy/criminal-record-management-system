from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app import models, schemas
from app.security import get_current_user, require_admin, require_any_role
from app.security import get_password_hash
from app.utils.audit import create_audit_log
from app.utils.reports import generate_analytics_excel, generate_analytics_report

router = APIRouter(prefix="/api/admin", tags=["admin"])


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
    if db.query(models.User).filter(models.User.username == data.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    if db.query(models.User).filter(models.User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email already exists")
    user = models.User(
        username=data.username,
        email=data.email,
        full_name=data.full_name,
        role=data.role,
        badge_number=data.badge_number,
        department=data.department,
        hashed_password=get_password_hash(data.password)
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    create_audit_log(db, "USER_CREATED", user_id=current_user.id, username=current_user.username, role=current_user.role,
                     resource_type="user", resource_id=user.id,
                     details={"created_username": data.username, "role": data.role})
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
    before = {"email": user.email, "full_name": user.full_name, "role": user.role.value, "badge_number": user.badge_number, "department": user.department, "is_active": user.is_active}
    role_changed = "role" in update_data and update_data["role"] != user.role
    if "password" in update_data:
        update_data["hashed_password"] = get_password_hash(update_data.pop("password"))
    for k, v in update_data.items():
        setattr(user, k, v)
    db.commit()
    db.refresh(user)
    after = {"email": user.email, "full_name": user.full_name, "role": user.role.value, "badge_number": user.badge_number, "department": user.department, "is_active": user.is_active}
    create_audit_log(db, "ROLE_CHANGED" if role_changed else "USER_UPDATED", user_id=current_user.id, username=current_user.username,
                     role=current_user.role, resource_type="user", resource_id=user_id,
                     reason="Administrative user update", details={"before": before, "after": after, "role_change": role_changed})
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
    db.delete(user)
    db.commit()
    create_audit_log(db, "USER_DELETED", user_id=current_user.id, username=current_user.username, role=current_user.role,
                     resource_type="user", resource_id=user_id)
    return {"message": "User deleted"}


# ── Audit Logs ───────────────────────────────────────────────────────────────
@router.get("/audit-logs", response_model=List[schemas.AuditLogOut])
async def list_audit_logs(
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    q = db.query(models.AuditLog)
    if action:
        q = q.filter(models.AuditLog.action.ilike(f"%{action}%"))
    if resource_type:
        q = q.filter(models.AuditLog.resource_type == resource_type)
    if user_id:
        q = q.filter(models.AuditLog.user_id == user_id)
    if status:
        q = q.filter(models.AuditLog.status == status)
    if date_from:
        q = q.filter(models.AuditLog.created_at >= date_from)
    if date_to:
        q = q.filter(models.AuditLog.created_at < date_to)
    return q.order_by(models.AuditLog.created_at.desc()).offset(skip).limit(limit).all()


# ── Dashboard Stats ───────────────────────────────────────────────────────────
@router.get("/dashboard", response_model=schemas.DashboardStats)
async def get_dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    from sqlalchemy import func
    from collections import defaultdict
    import json

    total_criminals = db.query(models.Criminal).count()
    total_cases = db.query(models.Case).count()
    open_cases = db.query(models.Case).filter(models.Case.status == "open").count()
    high_risk = db.query(models.Criminal).filter(models.Criminal.risk_score >= 75).count()
    pending_reviews = db.query(models.AIPrediction).filter(
        models.AIPrediction.review_status == "pending"
    ).count()
    unread_alerts = db.query(models.Notification).filter(
        models.Notification.is_read == False,
        models.Notification.notification_type == "alert"
    ).count()

    # Cases by status
    status_counts = db.query(
        models.Case.status, func.count(models.Case.id)
    ).group_by(models.Case.status).all()
    cases_by_status = {s.value: c for s, c in status_counts}

    # Crimes by type
    crime_counts = db.query(
        models.Criminal.crime_type, func.count(models.Criminal.id)
    ).filter(models.Criminal.crime_type != None).group_by(models.Criminal.crime_type).all()
    crimes_by_type = {ct: c for ct, c in crime_counts if ct}

    # Monthly cases (last 6 months)
    from datetime import datetime, timedelta
    monthly = []
    now = datetime.utcnow()
    for i in range(5, -1, -1):
        month_start = datetime(now.year, now.month, 1) - timedelta(days=i*30)
        month_end = month_start + timedelta(days=30)
        count = db.query(models.Case).filter(
            models.Case.created_at >= month_start,
            models.Case.created_at < month_end
        ).count()
        monthly.append({"month": month_start.strftime("%b %Y"), "cases": count})

    # Officer workload
    officer_workload_raw = db.query(
        models.User.full_name, func.count(models.Case.id).label('cases')
    ).join(models.Case, models.Case.assigned_officer_id == models.User.id, isouter=True
    ).filter(models.User.role == "investigating_officer"
    ).group_by(models.User.full_name).all()
    officer_workload = [{"officer": name, "cases": count} for name, count in officer_workload_raw]

    # AI prediction accuracy (confirmed / total reviewed)
    total_reviewed = db.query(models.AIPrediction).filter(
        models.AIPrediction.review_status != "pending"
    ).count()
    confirmed = db.query(models.AIPrediction).filter(
        models.AIPrediction.review_status == "confirmed"
    ).count()
    accuracy = round((confirmed / total_reviewed * 100) if total_reviewed > 0 else 0.0, 1)

    return schemas.DashboardStats(
        total_criminals=total_criminals,
        total_cases=total_cases,
        open_cases=open_cases,
        high_risk_criminals=high_risk,
        pending_reviews=pending_reviews,
        unread_alerts=unread_alerts,
        cases_by_status=cases_by_status,
        crimes_by_type=crimes_by_type,
        monthly_cases=monthly,
        officer_workload=officer_workload,
        prediction_accuracy=accuracy
    )


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
    setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
    if not setting:
        setting = models.SystemSetting(key=key, value=data.value, description=data.description)
        db.add(setting)
    else:
        setting.value = data.value
        if data.description is not None:
            setting.description = data.description
    
    setting.updated_by_id = current_user.id
    db.commit()
    db.refresh(setting)
    
    create_audit_log(db, "SETTING_UPDATED", user_id=current_user.id, username=current_user.username, role=current_user.role,
                     resource_type="system_setting", details={"key": key, "value": data.value})
    
    return setting


@router.get("/dashboard/report/excel")
async def export_dashboard_excel(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    from fastapi.responses import Response
    from sqlalchemy import func
    from datetime import datetime, timedelta

    analytics = _build_dashboard_analytics(db, func, datetime, timedelta)
    content = generate_analytics_excel(analytics)
    create_audit_log(db, "ANALYTICS_REPORT_EXCEL_GENERATED", user_id=current_user.id, username=current_user.username,
                     role=current_user.role, resource_type="dashboard")
    return Response(content=content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=ai_crms_dashboard_analytics.xlsx"})


@router.get("/dashboard/report/pdf")
async def export_dashboard_pdf(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    from fastapi.responses import Response
    from sqlalchemy import func
    from datetime import datetime, timedelta

    analytics = _build_dashboard_analytics(db, func, datetime, timedelta)
    content = generate_analytics_report(analytics)
    create_audit_log(db, "ANALYTICS_REPORT_PDF_GENERATED", user_id=current_user.id, username=current_user.username,
                     role=current_user.role, resource_type="dashboard")
    return Response(content=content, media_type="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=ai_crms_dashboard_analytics.pdf"})


def _build_dashboard_analytics(db, func, datetime, timedelta):
    total_criminals = db.query(models.Criminal).count()
    total_cases = db.query(models.Case).count()
    open_cases = db.query(models.Case).filter(models.Case.status == "open").count()
    high_risk = db.query(models.Criminal).filter(models.Criminal.risk_score >= 75).count()
    pending_reviews = db.query(models.AIPrediction).filter(models.AIPrediction.review_status == "pending").count()
    unread_alerts = db.query(models.Notification).filter(models.Notification.is_read == False, models.Notification.notification_type == "alert").count()
    status_counts = db.query(models.Case.status, func.count(models.Case.id)).group_by(models.Case.status).all()
    crime_counts = db.query(models.Criminal.crime_type, func.count(models.Criminal.id)).filter(models.Criminal.crime_type != None).group_by(models.Criminal.crime_type).all()
    now = datetime.utcnow()
    monthly = []
    for i in range(5, -1, -1):
        month_start = datetime(now.year, now.month, 1) - timedelta(days=i * 30)
        month_end = month_start + timedelta(days=30)
        count = db.query(models.Case).filter(models.Case.created_at >= month_start, models.Case.created_at < month_end).count()
        monthly.append({"month": month_start.strftime("%b %Y"), "cases": count})
    workload = db.query(models.User.full_name, func.count(models.Case.id).label('cases')).join(
        models.Case, models.Case.assigned_officer_id == models.User.id, isouter=True
    ).filter(models.User.role == "investigating_officer").group_by(models.User.full_name).all()
    total_reviewed = db.query(models.AIPrediction).filter(models.AIPrediction.review_status != "pending").count()
    confirmed = db.query(models.AIPrediction).filter(models.AIPrediction.review_status == "confirmed").count()
    accuracy = round((confirmed / total_reviewed * 100) if total_reviewed else 0.0, 1)
    return {
        "total_criminals": total_criminals, "total_cases": total_cases, "open_cases": open_cases,
        "high_risk_criminals": high_risk, "pending_reviews": pending_reviews, "unread_alerts": unread_alerts,
        "cases_by_status": {s.value: c for s, c in status_counts},
        "crimes_by_type": {ct: c for ct, c in crime_counts if ct},
        "monthly_cases": monthly,
        "officer_workload": [{"officer": name, "cases": count} for name, count in workload],
        "prediction_accuracy": accuracy,
    }
