from datetime import datetime, timezone
from difflib import SequenceMatcher
import secrets
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app import models, schemas
from app.constants import AI_ADVISORY_NOTICE, CRIME_CATEGORIES
from app.security import require_any_role, require_officer_or_admin, require_clerk_or_officer_or_admin
from app.utils.audit import create_audit_log
from app.utils.pagination import MAX_PAGE_SIZE, apply_sort, like_term, paginate

router = APIRouter(prefix="/api/criminals", tags=["criminals"])

# Advisory warnings use a loose threshold; blocking creation needs a strong
# match (near-identical name, or a similar name with the same date of birth).
DUPLICATE_THRESHOLD = 0.6
DUPLICATE_BLOCK_THRESHOLD = 0.9
CRIMINAL_SORT_FIELDS = {
    "created_at": models.Criminal.created_at,
    "last_name": models.Criminal.last_name,
    "first_name": models.Criminal.first_name,
    "crn": models.Criminal.crn,
    "prior_convictions": models.Criminal.prior_convictions,
    "threat_level": models.Criminal.threat_level,
}


def generate_crn():
    return "CRN" + "".join(secrets.choice("0123456789") for _ in range(8))


def _get_criminal(db: Session, criminal_id: int) -> models.Criminal:
    criminal = db.query(models.Criminal).filter(models.Criminal.id == criminal_id).first()
    if not criminal:
        raise HTTPException(status_code=404, detail="Criminal not found")
    return criminal


def _validate_gang(db: Session, gang_id: Optional[int]) -> None:
    if gang_id is not None and not db.query(models.Gang.id).filter(models.Gang.id == gang_id).first():
        raise HTTPException(status_code=422, detail="gang_id does not reference an existing gang")


def find_duplicates(db: Session, first_name: str, last_name: str, date_of_birth: Optional[datetime] = None,
                    exclude_id: Optional[int] = None):
    """Fuzzy name (+ date of birth) matching used both for warnings and create-time guards."""
    q = db.query(models.Criminal).filter(or_(
        func.lower(models.Criminal.last_name) == last_name.lower(),
        func.lower(models.Criminal.alias).like(like_term(last_name.lower()), escape="\\"),
        func.lower(models.Criminal.first_name) == first_name.lower(),
    ))
    if exclude_id is not None:
        q = q.filter(models.Criminal.id != exclude_id)
    full_name = f"{first_name} {last_name}".lower()
    matches = []
    for c in q.limit(500).all():
        score = SequenceMatcher(None, full_name, f"{c.first_name} {c.last_name}".lower()).ratio()
        if date_of_birth and c.date_of_birth:
            if abs((date_of_birth.replace(tzinfo=None) - c.date_of_birth.replace(tzinfo=None)).days) < 1:
                score = min(1.0, score + 0.3)
        if score >= DUPLICATE_THRESHOLD:
            matches.append((score, c))
    matches.sort(key=lambda item: -item[0])
    return matches


@router.get("", response_model=List[schemas.CriminalOut])
async def list_criminals(
    response: Response,
    search: Optional[str] = Query(None, max_length=100),
    crime_type: Optional[str] = Query(None, max_length=100),
    crime_category: Optional[str] = Query(None, max_length=50),
    threat_level: Optional[schemas.ThreatLevel] = Query(None),
    is_wanted: Optional[bool] = Query(None),
    gang_id: Optional[int] = Query(None, ge=1),
    sort: Optional[str] = Query(None, max_length=40),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    q = db.query(models.Criminal).options(selectinload(models.Criminal.gang))
    if search:
        term = like_term(search)
        q = q.filter(or_(
            models.Criminal.first_name.ilike(term, escape="\\"),
            models.Criminal.last_name.ilike(term, escape="\\"),
            models.Criminal.alias.ilike(term, escape="\\"),
            models.Criminal.crn.ilike(term, escape="\\"),
            models.Criminal.crime_type.ilike(term, escape="\\"),
        ))
    if crime_type:
        q = q.filter(models.Criminal.crime_type == crime_type)
    if crime_category:
        q = q.filter(models.Criminal.crime_category == crime_category)
    if threat_level:
        q = q.filter(models.Criminal.threat_level == threat_level.value)
    if is_wanted is not None:
        q = q.filter(models.Criminal.is_wanted == is_wanted)
    if gang_id:
        q = q.filter(models.Criminal.gang_id == gang_id)
    q = apply_sort(q, sort, CRIMINAL_SORT_FIELDS, models.Criminal.created_at.desc())
    return paginate(q, response, skip, limit)


@router.post("", response_model=schemas.CriminalOut)
async def create_criminal(
    data: schemas.CriminalCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_clerk_or_officer_or_admin)
):
    _validate_gang(db, data.gang_id)
    duplicates = [(score, c) for score, c in find_duplicates(db, data.first_name, data.last_name, data.date_of_birth)
                  if score >= DUPLICATE_BLOCK_THRESHOLD]
    if duplicates and not data.acknowledge_possible_duplicate:
        raise HTTPException(status_code=409, detail={
            "message": "Possible duplicate record(s) found. Review them, then resubmit with acknowledge_possible_duplicate=true if this is a different person.",
            "duplicates": [{"id": c.id, "crn": c.crn, "name": f"{c.first_name} {c.last_name}",
                            "match_score": round(score * 100, 1)} for score, c in duplicates[:5]],
        })

    crn = generate_crn()
    while db.query(models.Criminal.id).filter(models.Criminal.crn == crn).first():
        crn = generate_crn()

    payload = data.model_dump(exclude={"acknowledge_possible_duplicate"})
    payload["threat_level"] = data.threat_level.value
    if payload.get("crime_type") and not payload.get("crime_category"):
        payload["crime_category"] = CRIME_CATEGORIES.get(payload["crime_type"])

    try:
        criminal = models.Criminal(**payload, crn=crn, created_by_id=current_user.id)
        db.add(criminal)
        db.flush()
        db.add(models.CriminalHistory(
            criminal_id=criminal.id,
            event_type="record_created",
            description=f"Criminal record created by {current_user.full_name}"
                        + (" (possible duplicate acknowledged)" if duplicates else ""),
            date=datetime.now(timezone.utc),
            recorded_by=current_user.full_name,
        ))
        create_audit_log(db, "CRIMINAL_CREATED", actor=current_user, resource_type="criminal", resource_id=criminal.id,
                         details={"crn": crn, "possible_duplicates": [c.id for _, c in duplicates[:5]]}, commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(criminal)
    return criminal


@router.get("/check-duplicate", response_model=schemas.DuplicateCheckResult)
async def check_duplicate(
    first_name: str = Query(..., min_length=1, max_length=50),
    last_name: str = Query(..., min_length=1, max_length=50),
    date_of_birth: Optional[str] = Query(None, max_length=40),
    exclude_id: Optional[int] = Query(None, ge=1),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    dob = None
    if date_of_birth:
        try:
            dob = datetime.fromisoformat(date_of_birth.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(status_code=422, detail="date_of_birth must be an ISO-8601 date")
    matches = find_duplicates(db, first_name.strip(), last_name.strip(), dob, exclude_id)
    return schemas.DuplicateCheckResult(
        has_duplicates=bool(matches),
        duplicates=[schemas.CriminalOut.model_validate(c) for _, c in matches[:10]],
        match_score=round(matches[0][0] * 100, 1) if matches else 0.0,
    )


@router.get("/{criminal_id}", response_model=schemas.CriminalOut)
async def get_criminal(
    criminal_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    return _get_criminal(db, criminal_id)


@router.put("/{criminal_id}", response_model=schemas.CriminalOut)
async def update_criminal(
    criminal_id: int,
    data: schemas.CriminalUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_clerk_or_officer_or_admin)
):
    criminal = _get_criminal(db, criminal_id)
    update_data = data.model_dump(exclude_unset=True, exclude={"correction_reason"})
    if not update_data:
        raise HTTPException(status_code=422, detail="No changes supplied")
    for required in ("first_name", "last_name"):
        if required in update_data and not update_data[required]:
            raise HTTPException(status_code=422, detail=f"{required} cannot be empty")
    if "gang_id" in update_data:
        _validate_gang(db, update_data["gang_id"])
    if update_data.get("threat_level") is not None:
        update_data["threat_level"] = update_data["threat_level"].value
    # Status flags drive operational decisions; require an explicit reason.
    sensitive = {"is_wanted", "threat_level", "gang_id"} & set(update_data)
    if sensitive and not data.correction_reason:
        raise HTTPException(status_code=422, detail=f"correction_reason is required when changing {', '.join(sorted(sensitive))}")

    before = {k: getattr(criminal, k) for k in update_data}
    changed = {k for k, v in update_data.items() if getattr(criminal, k) != v}
    try:
        for k, v in update_data.items():
            setattr(criminal, k, v)
        db.add(models.CriminalHistory(
            criminal_id=criminal.id,
            event_type="record_corrected" if data.correction_reason else "record_updated",
            description=(f"Record updated by {current_user.full_name}. Fields: {', '.join(sorted(changed)) or 'none'}."
                         + (f" Reason: {data.correction_reason}" if data.correction_reason else "")),
            date=datetime.now(timezone.utc),
            recorded_by=current_user.full_name,
        ))
        after = {k: getattr(criminal, k) for k in update_data}
        create_audit_log(db, "CRIMINAL_UPDATED", actor=current_user, resource_type="criminal", resource_id=criminal_id,
                         reason=data.correction_reason, details={"before": before, "after": after}, commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(criminal)
    return criminal


@router.delete("/{criminal_id}")
async def delete_criminal(
    criminal_id: int,
    reason: str = Query(..., min_length=5, max_length=500, description="Why this record is being removed"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    if current_user.role.value not in ["admin", "record_clerk"]:
        raise HTTPException(status_code=403, detail="Not authorized to delete criminal records")
    criminal = _get_criminal(db, criminal_id)
    if db.query(models.AIPrediction.id).filter(models.AIPrediction.criminal_id == criminal_id).first():
        raise HTTPException(status_code=409, detail="This record has AI assessments on file and cannot be deleted; correct or annotate it instead.")
    if db.query(models.CaseCriminal.id).filter(models.CaseCriminal.criminal_id == criminal_id).first():
        raise HTTPException(status_code=409, detail="This record is linked to one or more cases; unlink it from those cases first.")
    snapshot = {"crn": criminal.crn}
    try:
        db.query(models.Notification).filter(models.Notification.related_criminal_id == criminal_id).update(
            {models.Notification.related_criminal_id: None}, synchronize_session=False)
        db.delete(criminal)
        create_audit_log(db, "CRIMINAL_DELETED", actor=current_user, resource_type="criminal", resource_id=criminal_id,
                         reason=reason, details=snapshot, commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"message": "Criminal record deleted"}


@router.get("/{criminal_id}/history", response_model=List[schemas.CriminalHistoryItem])
async def get_criminal_history(
    criminal_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    _get_criminal(db, criminal_id)
    return db.query(models.CriminalHistory).filter(
        models.CriminalHistory.criminal_id == criminal_id
    ).order_by(models.CriminalHistory.date.desc(), models.CriminalHistory.id.desc()).all()


@router.post("/{criminal_id}/history")
async def add_history_entry(
    criminal_id: int,
    data: schemas.CriminalHistoryCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_officer_or_admin)
):
    _get_criminal(db, criminal_id)
    hist = models.CriminalHistory(
        criminal_id=criminal_id,
        event_type=data.event_type,
        description=data.description,
        location=data.location,
        case_reference=data.case_reference,
        date=data.date or datetime.now(timezone.utc),
        recorded_by=current_user.full_name
    )
    db.add(hist)
    db.flush()
    create_audit_log(db, "CRIMINAL_HISTORY_ADDED", actor=current_user, resource_type="criminal_history", resource_id=hist.id,
                     details={"criminal_id": criminal_id, "event_type": data.event_type}, commit=False)
    db.commit()
    return {"message": "History entry added", "id": hist.id}


def _report_cases(db: Session, criminal_id: int):
    links = db.query(models.CaseCriminal).options(selectinload(models.CaseCriminal.case)).filter(
        models.CaseCriminal.criminal_id == criminal_id).all()
    return [{"case_number": cc.case.case_number, "status": cc.case.status.value,
             "crime_type": cc.case.crime_type, "role": cc.role} for cc in links]


def _include_ai(current_user: models.User) -> bool:
    # AI output is decision support for officers/admins; clerical exports omit it.
    return current_user.role.value in {"admin", "investigating_officer"}


@router.get("/{criminal_id}/report")
async def get_criminal_report(
    criminal_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    from app.utils.reports import generate_criminal_report

    criminal = _get_criminal(db, criminal_id)
    criminal_dict = {
        "id": criminal.id,
        "crn": criminal.crn,
        "first_name": criminal.first_name,
        "last_name": criminal.last_name,
        "date_of_birth": str(criminal.date_of_birth) if criminal.date_of_birth else None,
        "gender": criminal.gender,
        "nationality": criminal.nationality,
        "address": criminal.address,
        "phone": criminal.phone,
        "email": criminal.email,
        "occupation": criminal.occupation,
        "crime_type": criminal.crime_type,
        "crime_category": criminal.crime_category,
        "prior_convictions": criminal.prior_convictions,
        "modus_operandi": criminal.modus_operandi,
        "is_wanted": criminal.is_wanted,
        "is_incarcerated": criminal.is_incarcerated,
        "threat_level": criminal.threat_level,
        "risk_score": criminal.risk_score,
        "gang_name": criminal.gang.name if criminal.gang else None,
        "gang_rank": criminal.gang_rank,
        "prediction": None,
        "confidence": 0,
        "cases": _report_cases(db, criminal_id),
        "generated_by": f"{current_user.full_name} ({current_user.role.value})",
        "ai_advisory_notice": AI_ADVISORY_NOTICE,
    }
    pred_dicts = []
    if _include_ai(current_user):
        predictions = db.query(models.AIPrediction).filter(
            models.AIPrediction.criminal_id == criminal_id
        ).order_by(models.AIPrediction.created_at.desc()).limit(3).all()
        pred_dicts = [{"predicted_crime_type": p.predicted_crime_type,
                       "crime_type_confidence": p.crime_type_confidence,
                       "risk_score": p.risk_score,
                       "risk_level": p.risk_level,
                       "gang_affiliation_probability": p.gang_affiliation_probability,
                       "review_status": p.review_status.value} for p in predictions]
        if predictions:
            criminal_dict["prediction"] = predictions[0].predicted_crime_type
            criminal_dict["confidence"] = predictions[0].crime_type_confidence

    pdf_bytes = generate_criminal_report(criminal_dict, pred_dicts)
    create_audit_log(db, "REPORT_GENERATED", actor=current_user, resource_type="criminal", resource_id=criminal_id,
                     details={"format": "pdf", "includes_ai": _include_ai(current_user)})
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="criminal_{criminal.crn}.pdf"'}
    )


@router.get("/{criminal_id}/report/excel")
async def get_criminal_excel_report(
    criminal_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    from app.utils.reports import generate_criminal_excel

    criminal = _get_criminal(db, criminal_id)
    latest = None
    if _include_ai(current_user):
        latest = db.query(models.AIPrediction).filter(
            models.AIPrediction.criminal_id == criminal_id
        ).order_by(models.AIPrediction.created_at.desc()).first()
    data = {
        "crn": criminal.crn,
        "name": f"{criminal.first_name} {criminal.last_name}",
        "crime_category": criminal.crime_category,
        "prior_convictions": criminal.prior_convictions,
        "gang_name": criminal.gang.name if criminal.gang else None,
        "risk_score": criminal.risk_score,
        "prediction": latest.predicted_crime_type if latest else None,
        "confidence": latest.crime_type_confidence if latest else 0,
        "prediction_review_status": latest.review_status.value if latest else None,
        "cases": _report_cases(db, criminal_id),
    }
    xlsx = generate_criminal_excel(data)
    create_audit_log(db, "REPORT_EXCEL_GENERATED", actor=current_user, resource_type="criminal", resource_id=criminal_id,
                     details={"format": "xlsx", "includes_ai": _include_ai(current_user)})
    return Response(content=xlsx, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="criminal_{criminal.crn}.xlsx"'})
