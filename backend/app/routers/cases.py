from datetime import datetime, timezone
import secrets
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app import models, schemas
from app.security import (
    ensure_case_access, officer_can_access_case, require_admin, require_any_role,
    require_officer_or_admin,
)
from app.utils.audit import create_audit_log, create_notification
from app.utils.pagination import MAX_PAGE_SIZE, apply_sort, like_term, paginate
from app.utils.reports import generate_case_report, generate_case_excel

router = APIRouter(prefix="/api/cases", tags=["cases"])

CASE_SORT_FIELDS = {
    "created_at": models.Case.created_at,
    "incident_date": models.Case.incident_date,
    "priority": models.Case.priority,
    "status": models.Case.status,
    "title": models.Case.title,
    "case_number": models.Case.case_number,
}

# Allowed lifecycle transitions; anything else needs to go through an admin.
STATUS_TRANSITIONS = {
    models.CaseStatus.open: {models.CaseStatus.under_investigation, models.CaseStatus.closed},
    models.CaseStatus.under_investigation: {models.CaseStatus.open, models.CaseStatus.closed},
    models.CaseStatus.closed: {models.CaseStatus.under_investigation, models.CaseStatus.archived},
    models.CaseStatus.archived: set(),
}


def _random_digits(count: int) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(count))


def generate_case_number():
    return f"CASE/{datetime.now(timezone.utc).year}/{_random_digits(6)}"


def generate_fir_number():
    return f"FIR/{datetime.now(timezone.utc).year}/{_random_digits(5)}"


def _unique(db: Session, column, generator):
    for _ in range(20):
        candidate = generator()
        if not db.query(models.Case.id).filter(column == candidate).first():
            return candidate
    raise HTTPException(status_code=503, detail="Could not allocate a unique identifier; retry")


def _get_case(db: Session, case_id: int, user: models.User) -> models.Case:
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_access(user, case)
    return case


def _validate_officer(db: Session, officer_id: int) -> models.User:
    officer = db.query(models.User).filter(models.User.id == officer_id).first()
    if not officer or not officer.is_active or officer.role != models.UserRole.investigating_officer:
        raise HTTPException(status_code=422, detail="assigned officer must be an active investigating officer")
    return officer


def _load_criminals(db: Session, criminal_ids: List[int]) -> List[models.Criminal]:
    if len(set(criminal_ids)) != len(criminal_ids):
        raise HTTPException(status_code=422, detail="Duplicate criminal IDs are not allowed")
    if not criminal_ids:
        return []
    found = db.query(models.Criminal).filter(models.Criminal.id.in_(criminal_ids)).all()
    missing = sorted(set(criminal_ids) - {c.id for c in found})
    if missing:
        raise HTTPException(status_code=404, detail=f"Criminal(s) not found: {missing}")
    return found


@router.get("", response_model=List[schemas.CaseListItem])
async def list_cases(
    response: Response,
    search: Optional[str] = Query(None, max_length=100),
    status: Optional[schemas.CaseStatus] = Query(None),
    crime_type: Optional[str] = Query(None, max_length=100),
    priority: Optional[schemas.CasePriority] = Query(None),
    officer_id: Optional[int] = Query(None, ge=1),
    assigned_to_me: bool = Query(False),
    sort: Optional[str] = Query(None, max_length=40),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    q = db.query(models.Case).options(selectinload(models.Case.assigned_officer))
    if search:
        term = like_term(search)
        q = q.filter(or_(
            models.Case.title.ilike(term, escape="\\"),
            models.Case.case_number.ilike(term, escape="\\"),
            models.Case.fir_number.ilike(term, escape="\\"),
            models.Case.location.ilike(term, escape="\\"),
        ))
    if status:
        q = q.filter(models.Case.status == status.value)
    if crime_type:
        q = q.filter(models.Case.crime_type == crime_type)
    if priority:
        q = q.filter(models.Case.priority == priority.value)
    if officer_id:
        q = q.filter(models.Case.assigned_officer_id == officer_id)
    if assigned_to_me:
        q = q.filter(models.Case.assigned_officer_id == current_user.id)
    # Investigating officers only see their own cases plus unassigned ones.
    if current_user.role.value == "investigating_officer":
        q = q.filter(or_(models.Case.assigned_officer_id == current_user.id,
                         models.Case.assigned_officer_id.is_(None)))
    q = apply_sort(q, sort, CASE_SORT_FIELDS, models.Case.created_at.desc())
    return paginate(q, response, skip, limit)


@router.post("", response_model=schemas.CaseOut)
async def create_case(
    data: schemas.CaseCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_officer_or_admin)
):
    # Validate every reference before writing anything.
    criminals = _load_criminals(db, data.criminal_ids)
    if data.assigned_officer_id is not None:
        _validate_officer(db, data.assigned_officer_id)
        if current_user.role.value == "investigating_officer" and data.assigned_officer_id != current_user.id:
            raise HTTPException(status_code=403, detail="Officers can only assign new cases to themselves")
    if data.fir_number and db.query(models.Case.id).filter(models.Case.fir_number == data.fir_number).first():
        raise HTTPException(status_code=409, detail="A case with this FIR number already exists")

    case_data = data.model_dump(exclude={"criminal_ids"})
    case_data["case_number"] = _unique(db, models.Case.case_number, generate_case_number)
    case_data["fir_number"] = data.fir_number or _unique(db, models.Case.fir_number, generate_fir_number)
    case_data["created_by_id"] = current_user.id
    if case_data.get("priority") is not None:
        case_data["priority"] = case_data["priority"].value

    try:
        case = models.Case(**case_data)
        db.add(case)
        db.flush()
        for criminal in criminals:
            db.add(models.CaseCriminal(case_id=case.id, criminal_id=criminal.id, role="suspect"))
        create_audit_log(db, "CASE_CREATED", actor=current_user, resource_type="case", resource_id=case.id,
                         details={"case_number": case.case_number, "title": data.title,
                                  "criminal_ids": data.criminal_ids}, commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(case)
    return case


@router.get("/{case_id}", response_model=schemas.CaseOut)
async def get_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    return _get_case(db, case_id, current_user)


@router.put("/{case_id}", response_model=schemas.CaseOut)
async def update_case(
    case_id: int,
    data: schemas.CaseUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_officer_or_admin)
):
    case = _get_case(db, case_id, current_user)
    update_data = data.model_dump(exclude_unset=True, exclude={"criminal_ids", "status_reason"})

    if "assigned_officer_id" in update_data and update_data["assigned_officer_id"] is not None:
        _validate_officer(db, update_data["assigned_officer_id"])
        if current_user.role.value == "investigating_officer" and update_data["assigned_officer_id"] != current_user.id:
            raise HTTPException(status_code=403, detail="Use the assignment endpoint; officers cannot reassign cases to others")
    if "fir_number" in update_data and update_data["fir_number"] and update_data["fir_number"] != case.fir_number:
        if db.query(models.Case.id).filter(models.Case.fir_number == update_data["fir_number"]).first():
            raise HTTPException(status_code=409, detail="A case with this FIR number already exists")

    if "status" in update_data and update_data["status"] is not None:
        new_status = models.CaseStatus(update_data["status"].value)
        if new_status != case.status:
            if new_status not in STATUS_TRANSITIONS[case.status] and current_user.role.value != "admin":
                raise HTTPException(status_code=409, detail=f"Cannot move a case from {case.status.value} to {new_status.value}")
            if new_status == models.CaseStatus.closed and not data.status_reason:
                raise HTTPException(status_code=422, detail="status_reason is required when closing a case")
            update_data["closed_at"] = datetime.now(timezone.utc) if new_status == models.CaseStatus.closed else case.closed_at
        update_data["status"] = new_status
    if update_data.get("priority") is not None:
        update_data["priority"] = update_data["priority"].value

    criminals = _load_criminals(db, data.criminal_ids) if data.criminal_ids is not None else None

    before = {k: getattr(case, k) for k in update_data.keys()}
    try:
        for k, v in update_data.items():
            setattr(case, k, v)
        if criminals is not None:
            existing = {cc.criminal_id: cc for cc in case.criminals}
            wanted = {c.id for c in criminals}
            for criminal_id, link in existing.items():
                if criminal_id not in wanted:
                    db.delete(link)
            for criminal_id in wanted - set(existing):
                db.add(models.CaseCriminal(case_id=case.id, criminal_id=criminal_id, role="suspect"))
        after = {k: getattr(case, k) for k in update_data.keys()}
        create_audit_log(db, "CASE_UPDATED", actor=current_user, resource_type="case", resource_id=case_id,
                         reason=data.status_reason,
                         details={"before": before, "after": after,
                                  "criminal_ids": data.criminal_ids}, commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(case)
    return case


@router.delete("/{case_id}")
async def delete_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    reviewed = db.query(models.AIPredictionReview.id).join(
        models.AIPrediction, models.AIPrediction.id == models.AIPredictionReview.prediction_id
    ).filter(models.AIPrediction.case_id == case_id).first()
    if reviewed:
        raise HTTPException(
            status_code=409,
            detail="This case has AI review history, which is retained for accountability. Archive the case instead of deleting it.",
        )
    snapshot = {"case_number": case.case_number, "title": case.title, "status": case.status.value}
    try:
        db.delete(case)
        create_audit_log(db, "CASE_DELETED", actor=current_user, resource_type="case", resource_id=case_id,
                         details=snapshot, commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"message": "Case deleted"}


@router.post("/{case_id}/assign")
async def assign_officer(
    case_id: int,
    officer_id: Optional[int] = Query(None, ge=1, description="Deprecated: send JSON body {officer_id}"),
    body: Optional[schemas.CaseAssignment] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_officer_or_admin)
):
    target_id = body.officer_id if body else officer_id
    if target_id is None:
        raise HTTPException(status_code=422, detail="officer_id is required")
    case = _get_case(db, case_id, current_user)
    officer = _validate_officer(db, target_id)
    if current_user.role.value == "investigating_officer" and target_id != current_user.id:
        raise HTTPException(status_code=403, detail="Officers can only assign cases to themselves; ask an admin to reassign")
    previous = case.assigned_officer_id
    case.assigned_officer_id = target_id
    if case.status == models.CaseStatus.open:
        case.status = models.CaseStatus.under_investigation
    create_audit_log(db, "OFFICER_ASSIGNED", actor=current_user, resource_type="case", resource_id=case_id,
                     details={"officer_id": target_id, "previous_officer_id": previous}, commit=False)
    db.commit()
    if target_id != current_user.id:
        create_notification(
            db, title=f"Case assigned: {case.case_number}",
            message=f"You have been assigned to case {case.case_number} ({case.title}).",
            notification_type="info", target_user_id=target_id, related_case_id=case.id,
            dedup_key=f"case-assigned:{case.id}:{target_id}",
        )
    return {"message": f"Officer {officer.full_name} assigned to case {case.case_number}"}


@router.post("/{case_id}/criminals")
async def add_criminal_to_case(
    case_id: int,
    criminal_id: Optional[int] = Query(None, ge=1, description="Deprecated: send JSON body"),
    role: Optional[str] = Query(None, description="Deprecated: send JSON body"),
    body: Optional[schemas.CaseCriminalLink] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_officer_or_admin)
):
    if body is None:
        if criminal_id is None:
            raise HTTPException(status_code=422, detail="criminal_id is required")
        body = schemas.CaseCriminalLink(criminal_id=criminal_id, role=role or "suspect")
    case = _get_case(db, case_id, current_user)
    criminal = db.query(models.Criminal).filter(models.Criminal.id == body.criminal_id).first()
    if not criminal:
        raise HTTPException(status_code=404, detail="Criminal not found")
    existing = db.query(models.CaseCriminal).filter(
        models.CaseCriminal.case_id == case.id,
        models.CaseCriminal.criminal_id == body.criminal_id
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Criminal already linked to this case")
    cc = models.CaseCriminal(case_id=case.id, criminal_id=body.criminal_id, role=body.role)
    db.add(cc)
    db.flush()
    create_audit_log(db, "CRIMINAL_LINKED_TO_CASE", actor=current_user, resource_type="case_criminal", resource_id=cc.id,
                     details={"case_id": case.id, "criminal_id": body.criminal_id, "role": body.role}, commit=False)
    db.commit()
    return {"message": "Criminal linked to case", "id": cc.id}


@router.delete("/{case_id}/criminals/{criminal_id}")
async def remove_criminal_from_case(
    case_id: int,
    criminal_id: int,
    reason: str = Query(..., min_length=5, max_length=500),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_officer_or_admin),
):
    case = _get_case(db, case_id, current_user)
    link = db.query(models.CaseCriminal).filter(
        models.CaseCriminal.case_id == case.id, models.CaseCriminal.criminal_id == criminal_id
    ).first()
    if not link:
        raise HTTPException(status_code=404, detail="Criminal is not linked to this case")
    db.delete(link)
    create_audit_log(db, "CRIMINAL_UNLINKED_FROM_CASE", actor=current_user, resource_type="case", resource_id=case.id,
                     reason=reason, details={"criminal_id": criminal_id, "role": link.role}, commit=False)
    db.commit()
    return {"message": "Criminal unlinked from case"}


@router.post("/{case_id}/evidence", response_model=schemas.EvidenceOut)
async def add_evidence(
    case_id: int,
    data: schemas.EvidenceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_officer_or_admin)
):
    case = _get_case(db, case_id, current_user)
    suffix = case.case_number.split('/')[-1]
    for _ in range(20):
        ev_num = f"EV/{suffix}/{_random_digits(4)}"
        if not db.query(models.Evidence.id).filter(models.Evidence.case_id == case.id,
                                                   models.Evidence.evidence_number == ev_num).first():
            break
    else:
        raise HTTPException(status_code=503, detail="Could not allocate an evidence number; retry")

    payload = data.model_dump()
    payload["status"] = data.status.value
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    custody = f"[{stamp}] Logged by {current_user.full_name} ({current_user.username})"
    payload["chain_of_custody"] = f"{custody}\n{data.chain_of_custody}" if data.chain_of_custody else custody
    evidence = models.Evidence(case_id=case.id, evidence_number=ev_num, created_by_id=current_user.id, **payload)
    db.add(evidence)
    db.flush()
    create_audit_log(db, "EVIDENCE_ADDED", actor=current_user, resource_type="evidence", resource_id=evidence.id,
                     details={"case_id": case.id, "evidence_number": ev_num, "type": data.type,
                              "file_sha256": data.file_sha256}, commit=False)
    db.commit()
    db.refresh(evidence)
    return evidence


@router.put("/{case_id}/evidence/{evidence_id}", response_model=schemas.EvidenceOut)
async def update_evidence(
    case_id: int, evidence_id: int, data: schemas.EvidenceUpdate,
    db: Session = Depends(get_db), current_user: models.User = Depends(require_officer_or_admin)
):
    case = _get_case(db, case_id, current_user)
    evidence = db.query(models.Evidence).filter(models.Evidence.id == evidence_id, models.Evidence.case_id == case.id).first()
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")
    changes = data.model_dump(exclude_unset=True, exclude={"custody_note"})
    if "status" in changes and changes["status"] is not None:
        changes["status"] = changes["status"].value
    if not changes and not data.custody_note:
        raise HTTPException(status_code=422, detail="No changes supplied")
    before = {k: getattr(evidence, k) for k in changes}
    for k, v in changes.items():
        setattr(evidence, k, v)
    # Chain of custody is append-only: every change adds a dated line.
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    summary = ", ".join(f"{k}={v}" for k, v in changes.items() if k in {"status", "location_found"})
    note = data.custody_note or (f"Updated ({summary})" if summary else "Record updated")
    evidence.chain_of_custody = f"{evidence.chain_of_custody or ''}\n[{stamp}] {current_user.full_name}: {note}".strip()
    after = {k: getattr(evidence, k) for k in changes}
    create_audit_log(db, "EVIDENCE_UPDATED", actor=current_user, resource_type="evidence", resource_id=evidence.id,
                     details={"case_id": case.id, "before": before, "after": after}, commit=False)
    db.commit()
    db.refresh(evidence)
    return evidence


@router.post("/{case_id}/victims", response_model=schemas.VictimOut)
async def add_victim(
    case_id: int,
    data: schemas.VictimCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_officer_or_admin)
):
    case = _get_case(db, case_id, current_user)
    payload = data.model_dump()
    payload["status"] = data.status.value
    victim = models.Victim(case_id=case.id, **payload)
    db.add(victim)
    db.flush()
    create_audit_log(db, "VICTIM_ADDED", actor=current_user, resource_type="victim", resource_id=victim.id,
                     details={"case_id": case.id}, commit=False)
    db.commit()
    db.refresh(victim)
    return victim


def _case_report_dict(case: models.Case, current_user: models.User) -> dict:
    return {
        "case_number": case.case_number,
        "title": case.title,
        "status": case.status.value,
        "priority": case.priority,
        "crime_type": case.crime_type,
        "crime_category": case.crime_category,
        "location": case.location,
        "incident_date": str(case.incident_date) if case.incident_date else None,
        "fir_number": case.fir_number,
        "fir_date": str(case.fir_date) if case.fir_date else None,
        "officer_name": case.assigned_officer.full_name if case.assigned_officer else "Unassigned",
        "generated_by": f"{current_user.full_name} ({current_user.role.value})",
        "criminals": [
            {"criminal": {
                "first_name": cc.criminal.first_name,
                "last_name": cc.criminal.last_name,
                "crn": cc.criminal.crn,
                "crime_type": cc.criminal.crime_type,
                "risk_score": cc.criminal.risk_score
            }, "role": cc.role}
            for cc in case.criminals
        ],
        "evidence": [
            {"evidence_number": e.evidence_number, "type": e.type,
             "description": e.description, "collected_by": e.collected_by,
             "status": e.status}
            for e in case.evidence
        ],
        "victims": [
            {"name": f"{v.first_name} {v.last_name}", "age": v.age, "gender": v.gender,
             "status": v.status, "injury_description": v.injury_description}
            for v in case.victims
        ]
    }


def _download_name(case: models.Case, extension: str) -> str:
    return f"case_{case.case_number.replace('/', '_')}.{extension}"


@router.get("/{case_id}/report")
async def get_case_report(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    case = _get_case(db, case_id, current_user)
    pdf_bytes = generate_case_report(_case_report_dict(case, current_user))
    create_audit_log(db, "CASE_REPORT_GENERATED", actor=current_user, resource_type="case", resource_id=case_id,
                     details={"format": "pdf"})
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{_download_name(case, "pdf")}"'}
    )


@router.get("/{case_id}/report/excel")
async def get_case_excel_report(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    case = _get_case(db, case_id, current_user)
    xlsx = generate_case_excel(_case_report_dict(case, current_user))
    create_audit_log(db, "CASE_REPORT_EXCEL_GENERATED", actor=current_user, resource_type="case", resource_id=case_id,
                     details={"format": "xlsx"})
    return Response(content=xlsx, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{_download_name(case, "xlsx")}"'})


__all__ = ["router", "officer_can_access_case"]
