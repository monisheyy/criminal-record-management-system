from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from typing import List, Optional
from datetime import datetime
import random
import string
from app.database import get_db
from app import models, schemas
from app.security import get_current_user, require_any_role
from app.utils.audit import create_audit_log, create_notification

router = APIRouter(prefix="/api/criminals", tags=["criminals"])


def generate_crn():
    return "CRN" + "".join(random.choices(string.digits, k=8))


@router.get("", response_model=List[schemas.CriminalOut])
async def list_criminals(
    search: Optional[str] = Query(None),
    crime_type: Optional[str] = Query(None),
    crime_category: Optional[str] = Query(None),
    threat_level: Optional[str] = Query(None),
    is_wanted: Optional[bool] = Query(None),
    gang_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    q = db.query(models.Criminal)
    if search:
        term = f"%{search}%"
        q = q.filter(or_(
            models.Criminal.first_name.ilike(term),
            models.Criminal.last_name.ilike(term),
            models.Criminal.alias.ilike(term),
            models.Criminal.crn.ilike(term),
            models.Criminal.crime_type.ilike(term),
        ))
    if crime_type:
        q = q.filter(models.Criminal.crime_type == crime_type)
    if crime_category:
        q = q.filter(models.Criminal.crime_category == crime_category)
    if threat_level:
        q = q.filter(models.Criminal.threat_level == threat_level)
    if is_wanted is not None:
        q = q.filter(models.Criminal.is_wanted == is_wanted)
    if gang_id:
        q = q.filter(models.Criminal.gang_id == gang_id)
    return q.order_by(models.Criminal.created_at.desc()).offset(skip).limit(limit).all()


@router.post("", response_model=schemas.CriminalOut)
async def create_criminal(
    data: schemas.CriminalCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    crn = generate_crn()
    while db.query(models.Criminal).filter(models.Criminal.crn == crn).first():
        crn = generate_crn()

    criminal = models.Criminal(**data.model_dump(), crn=crn, created_by_id=current_user.id)
    db.add(criminal)
    db.commit()
    db.refresh(criminal)

    # History entry
    hist = models.CriminalHistory(
        criminal_id=criminal.id,
        event_type="record_created",
        description=f"Criminal record created by {current_user.full_name}",
        date=datetime.utcnow(),
        recorded_by=current_user.full_name
    )
    db.add(hist)
    db.commit()

    create_audit_log(db, "CRIMINAL_CREATED", user_id=current_user.id, username=current_user.username,
                     resource_type="criminal", resource_id=criminal.id,
                     details={"crn": crn, "name": f"{data.first_name} {data.last_name}"})
    return criminal


@router.get("/check-duplicate", response_model=schemas.DuplicateCheckResult)
async def check_duplicate(
    first_name: str = Query(...),
    last_name: str = Query(...),
    date_of_birth: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    q = db.query(models.Criminal)
    term = f"%{last_name}%"
    matches = q.filter(
        or_(
            func.lower(models.Criminal.last_name).like(last_name.lower()),
            func.lower(models.Criminal.alias).like(f"%{last_name.lower()}%")
        )
    ).all()

    # Fuzzy name match scoring
    from difflib import SequenceMatcher
    full_name = f"{first_name} {last_name}".lower()
    duplicates = []
    best_score = 0.0
    for c in matches:
        c_name = f"{c.first_name} {c.last_name}".lower()
        score = SequenceMatcher(None, full_name, c_name).ratio()
        if date_of_birth and c.date_of_birth:
            try:
                dob = datetime.fromisoformat(date_of_birth.replace('Z', '+00:00'))
                if abs((dob.replace(tzinfo=None) - c.date_of_birth.replace(tzinfo=None)).days) < 1:
                    score = min(1.0, score + 0.3)
            except Exception:
                pass
        if score >= 0.6:
            duplicates.append(c)
            best_score = max(best_score, score)

    return schemas.DuplicateCheckResult(
        has_duplicates=len(duplicates) > 0,
        duplicates=[schemas.CriminalOut.model_validate(c) for c in duplicates],
        match_score=round(best_score * 100, 1)
    )


@router.get("/{criminal_id}", response_model=schemas.CriminalOut)
async def get_criminal(
    criminal_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    criminal = db.query(models.Criminal).filter(models.Criminal.id == criminal_id).first()
    if not criminal:
        raise HTTPException(status_code=404, detail="Criminal not found")
    return criminal


@router.put("/{criminal_id}", response_model=schemas.CriminalOut)
async def update_criminal(
    criminal_id: int,
    data: schemas.CriminalUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    criminal = db.query(models.Criminal).filter(models.Criminal.id == criminal_id).first()
    if not criminal:
        raise HTTPException(status_code=404, detail="Criminal not found")

    update_data = data.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(criminal, k, v)
    db.commit()
    db.refresh(criminal)

    hist = models.CriminalHistory(
        criminal_id=criminal.id,
        event_type="record_updated",
        description=f"Record updated by {current_user.full_name}",
        date=datetime.utcnow(),
        recorded_by=current_user.full_name
    )
    db.add(hist)
    db.commit()

    create_audit_log(db, "CRIMINAL_UPDATED", user_id=current_user.id, username=current_user.username,
                     resource_type="criminal", resource_id=criminal_id)
    return criminal


@router.delete("/{criminal_id}")
async def delete_criminal(
    criminal_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    criminal = db.query(models.Criminal).filter(models.Criminal.id == criminal_id).first()
    if not criminal:
        raise HTTPException(status_code=404, detail="Criminal not found")
    if current_user.role.value not in ["admin", "record_clerk"]:
        raise HTTPException(status_code=403, detail="Not authorized to delete criminal records")
    db.delete(criminal)
    db.commit()
    create_audit_log(db, "CRIMINAL_DELETED", user_id=current_user.id, username=current_user.username,
                     resource_type="criminal", resource_id=criminal_id)
    return {"message": "Criminal record deleted"}


@router.get("/{criminal_id}/history", response_model=List[schemas.CriminalHistoryItem])
async def get_criminal_history(
    criminal_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    criminal = db.query(models.Criminal).filter(models.Criminal.id == criminal_id).first()
    if not criminal:
        raise HTTPException(status_code=404, detail="Criminal not found")
    return db.query(models.CriminalHistory).filter(
        models.CriminalHistory.criminal_id == criminal_id
    ).order_by(models.CriminalHistory.date.desc()).all()


@router.post("/{criminal_id}/history")
async def add_history_entry(
    criminal_id: int,
    event_type: str,
    description: str,
    location: Optional[str] = None,
    case_reference: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    hist = models.CriminalHistory(
        criminal_id=criminal_id,
        event_type=event_type,
        description=description,
        location=location,
        case_reference=case_reference,
        date=datetime.utcnow(),
        recorded_by=current_user.full_name
    )
    db.add(hist)
    db.commit()
    return {"message": "History entry added"}


@router.get("/{criminal_id}/report")
async def get_criminal_report(
    criminal_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    from fastapi.responses import Response
    from app.utils.reports import generate_criminal_report

    criminal = db.query(models.Criminal).filter(models.Criminal.id == criminal_id).first()
    if not criminal:
        raise HTTPException(status_code=404, detail="Criminal not found")

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
    }
    predictions = db.query(models.AIPrediction).filter(
        models.AIPrediction.criminal_id == criminal_id
    ).order_by(models.AIPrediction.created_at.desc()).limit(3).all()
    pred_dicts = [{"predicted_crime_type": p.predicted_crime_type,
                   "crime_type_confidence": p.crime_type_confidence,
                   "risk_score": p.risk_score,
                   "risk_level": p.risk_level,
                   "gang_affiliation_probability": p.gang_affiliation_probability,
                   "review_status": p.review_status.value} for p in predictions]

    pdf_bytes = generate_criminal_report(criminal_dict, pred_dicts)
    create_audit_log(db, "CRIMINAL_REPORT_GENERATED", user_id=current_user.id,
                     username=current_user.username, resource_type="criminal", resource_id=criminal_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=criminal_{criminal.crn}.pdf"}
    )
