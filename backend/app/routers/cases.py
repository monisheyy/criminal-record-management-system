from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional
from datetime import datetime
import random
import string
from app.database import get_db
from app import models, schemas
from app.security import require_any_role, require_officer_or_admin
from app.utils.audit import create_audit_log, create_notification
from app.utils.reports import generate_case_report, generate_case_excel

router = APIRouter(prefix="/api/cases", tags=["cases"])


def generate_case_number():
    year = datetime.utcnow().year
    return f"CASE/{year}/" + "".join(random.choices(string.digits, k=6))


def generate_fir_number():
    year = datetime.utcnow().year
    return f"FIR/{year}/" + "".join(random.choices(string.digits, k=5))


@router.get("", response_model=List[schemas.CaseOut])
async def list_cases(
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    crime_type: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    officer_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    q = db.query(models.Case)
    if search:
        term = f"%{search}%"
        q = q.filter(or_(
            models.Case.title.ilike(term),
            models.Case.case_number.ilike(term),
            models.Case.fir_number.ilike(term),
            models.Case.location.ilike(term),
        ))
    if status:
        q = q.filter(models.Case.status == status)
    if crime_type:
        q = q.filter(models.Case.crime_type == crime_type)
    if priority:
        q = q.filter(models.Case.priority == priority)
    if officer_id:
        q = q.filter(models.Case.assigned_officer_id == officer_id)
    # Investigating officers only see their own cases unless admin
    if current_user.role.value == "investigating_officer":
        q = q.filter(
            or_(models.Case.assigned_officer_id == current_user.id,
                models.Case.assigned_officer_id == None)
        )
    return q.order_by(models.Case.created_at.desc()).offset(skip).limit(limit).all()


@router.post("", response_model=schemas.CaseOut)
async def create_case(
    data: schemas.CaseCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_officer_or_admin)
):
    case_number = generate_case_number()
    while db.query(models.Case).filter(models.Case.case_number == case_number).first():
        case_number = generate_case_number()

    fir_number = data.fir_number or generate_fir_number()

    criminal_ids = list(dict.fromkeys(data.criminal_ids or []))
    if len(criminal_ids) != len(data.criminal_ids or []):
        raise HTTPException(status_code=400, detail="Duplicate criminal IDs are not allowed")

    criminals = []
    for cid in criminal_ids:
        criminal = db.query(models.Criminal).filter(models.Criminal.id == cid).first()
        if not criminal:
            raise HTTPException(status_code=404, detail=f"Criminal {cid} not found")
        criminals.append(criminal)

    case_data = data.model_dump(exclude={"criminal_ids"})
    case_data["case_number"] = case_number
    case_data["fir_number"] = fir_number
    case_data["created_by_id"] = current_user.id

    case = models.Case(**case_data)
    db.add(case)
    db.flush()

    for criminal in criminals:
        db.add(models.CaseCriminal(case_id=case.id, criminal_id=criminal.id, role="suspect"))

    db.commit()
    db.refresh(case)

    create_audit_log(db, "CASE_CREATED", user_id=current_user.id, username=current_user.username, role=current_user.role,
                     resource_type="case", resource_id=case.id,
                     details={"case_number": case_number, "title": data.title})
    return case


@router.get("/{case_id}", response_model=schemas.CaseOut)
async def get_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if current_user.role.value == "investigating_officer" and case.assigned_officer_id not in (None, current_user.id):
        raise HTTPException(status_code=403, detail="You are not assigned to this case")
    return case


@router.put("/{case_id}", response_model=schemas.CaseOut)
async def update_case(
    case_id: int,
    data: schemas.CaseUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_officer_or_admin)
):
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if current_user.role.value == "investigating_officer" and case.assigned_officer_id not in (None, current_user.id):
        raise HTTPException(status_code=403, detail="You are not assigned to this case")

    update_data = data.model_dump(exclude_unset=True, exclude={"criminal_ids"})
    before = {k: getattr(case, k) for k in update_data.keys()}

    # Handle status transition
    if "status" in update_data and update_data["status"] == "closed":
        update_data["closed_at"] = datetime.utcnow()

    for k, v in update_data.items():
        setattr(case, k, v)

    # Update linked criminals if provided
    if data.criminal_ids is not None:
        for cid in data.criminal_ids:
            if not db.query(models.Criminal).filter(models.Criminal.id == cid).first():
                db.rollback()
                raise HTTPException(status_code=404, detail=f"Criminal {cid} not found")
        db.query(models.CaseCriminal).filter(models.CaseCriminal.case_id == case_id).delete()
        for cid in data.criminal_ids:
            cc = models.CaseCriminal(case_id=case_id, criminal_id=cid, role="suspect")
            db.add(cc)

    db.commit()
    db.refresh(case)
    after = {k: getattr(case, k) for k in update_data.keys()}
    create_audit_log(db, "CASE_UPDATED", user_id=current_user.id, username=current_user.username, role=current_user.role,
                     resource_type="case", resource_id=case_id, details={"before": before, "after": after})
    return case


@router.delete("/{case_id}")
async def delete_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    if current_user.role.value not in ["admin"]:
        raise HTTPException(status_code=403, detail="Only admins can delete cases")
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    db.delete(case)
    db.commit()
    create_audit_log(db, "CASE_DELETED", user_id=current_user.id, username=current_user.username, role=current_user.role,
                     resource_type="case", resource_id=case_id)
    return {"message": "Case deleted"}


@router.post("/{case_id}/assign")
async def assign_officer(
    case_id: int,
    officer_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_officer_or_admin)
):
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    officer = db.query(models.User).filter(models.User.id == officer_id).first()
    if not officer or officer.role.value != "investigating_officer":
        raise HTTPException(status_code=404, detail="Officer not found")
    if current_user.role.value == "investigating_officer" and case.assigned_officer_id not in (None, current_user.id):
        raise HTTPException(status_code=403, detail="You are not assigned to this case")
    case.assigned_officer_id = officer_id
    if case.status == models.CaseStatus.open:
        case.status = models.CaseStatus.under_investigation
    db.commit()
    create_audit_log(db, "OFFICER_ASSIGNED", user_id=current_user.id, username=current_user.username, role=current_user.role,
                     resource_type="case", resource_id=case_id,
                     details={"officer_id": officer_id, "officer_name": officer.full_name})
    return {"message": f"Officer {officer.full_name} assigned to case {case.case_number}"}


@router.post("/{case_id}/criminals")
async def add_criminal_to_case(
    case_id: int,
    criminal_id: int,
    role: str = "suspect",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_officer_or_admin)
):
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if current_user.role.value == "investigating_officer" and case.assigned_officer_id not in (None, current_user.id):
        raise HTTPException(status_code=403, detail="You are not assigned to this case")
    criminal = db.query(models.Criminal).filter(models.Criminal.id == criminal_id).first()
    if not criminal:
        raise HTTPException(status_code=404, detail="Criminal not found")
    existing = db.query(models.CaseCriminal).filter(
        models.CaseCriminal.case_id == case_id,
        models.CaseCriminal.criminal_id == criminal_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Criminal already linked to this case")
    cc = models.CaseCriminal(case_id=case_id, criminal_id=criminal_id, role=role)
    db.add(cc)
    db.commit()
    create_audit_log(db, "CRIMINAL_LINKED_TO_CASE", user_id=current_user.id, username=current_user.username, role=current_user.role,
                     resource_type="case_criminal", resource_id=cc.id, details={"case_id": case_id, "criminal_id": criminal_id, "role": role})
    return {"message": "Criminal linked to case"}


@router.post("/{case_id}/evidence", response_model=schemas.EvidenceOut)
async def add_evidence(
    case_id: int,
    data: schemas.EvidenceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_officer_or_admin)
):
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ev_num = f"EV/{case.case_number.split('/')[-1]}/{''.join(random.choices(string.digits, k=4))}"
    evidence = models.Evidence(case_id=case_id, evidence_number=ev_num, **data.model_dump())
    db.add(evidence)
    db.commit()
    db.refresh(evidence)
    create_audit_log(db, "EVIDENCE_ADDED", user_id=current_user.id, username=current_user.username, role=current_user.role,
                     resource_type="evidence", resource_id=evidence.id)
    return evidence


@router.post("/{case_id}/victims", response_model=schemas.VictimOut)
async def add_victim(
    case_id: int,
    data: schemas.VictimCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_officer_or_admin)
):
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    victim = models.Victim(case_id=case_id, **data.model_dump())
    db.add(victim)
    db.commit()
    db.refresh(victim)
    create_audit_log(db, "VICTIM_ADDED", user_id=current_user.id, username=current_user.username, role=current_user.role,
                     resource_type="victim", resource_id=victim.id)
    return victim


@router.get("/{case_id}/report")
async def get_case_report(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if current_user.role.value == "investigating_officer" and case.assigned_officer_id not in (None, current_user.id):
        raise HTTPException(status_code=403, detail="You are not assigned to this case")

    case_dict = {
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
    pdf_bytes = generate_case_report(case_dict)
    create_audit_log(db, "CASE_REPORT_GENERATED", user_id=current_user.id,
                     username=current_user.username, resource_type="case", resource_id=case_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=case_{case.case_number.replace('/', '_')}.pdf"}
    )


@router.put("/{case_id}/evidence/{evidence_id}", response_model=schemas.EvidenceOut)
async def update_evidence(
    case_id: int, evidence_id: int, data: schemas.EvidenceCreate,
    db: Session = Depends(get_db), current_user: models.User = Depends(require_officer_or_admin)
):
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if current_user.role.value == "investigating_officer" and case.assigned_officer_id not in (None, current_user.id):
        raise HTTPException(status_code=403, detail="You are not assigned to this case")
    evidence = db.query(models.Evidence).filter(models.Evidence.id == evidence_id, models.Evidence.case_id == case_id).first()
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")
    before = {k: getattr(evidence, k) for k in data.model_dump(exclude_unset=True).keys()}
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(evidence, k, v)
    db.commit(); db.refresh(evidence)
    after = {k: getattr(evidence, k) for k in data.model_dump(exclude_unset=True).keys()}
    create_audit_log(db, "EVIDENCE_UPDATED", user_id=current_user.id, username=current_user.username, role=current_user.role,
                     resource_type="evidence", resource_id=evidence.id, details={"before": before, "after": after})
    return evidence


@router.get("/{case_id}/report/excel")
async def get_case_excel_report(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    from fastapi.responses import Response

    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if current_user.role.value == "investigating_officer" and case.assigned_officer_id not in (None, current_user.id):
        raise HTTPException(status_code=403, detail="You are not assigned to this case")

    case_dict = {
        "case_number": case.case_number, "fir_number": case.fir_number,
        "fir_date": str(case.fir_date) if case.fir_date else None,
        "status": case.status.value,
        "officer_name": case.assigned_officer.full_name if case.assigned_officer else "Unassigned",
        "criminals": [{"criminal": {"crn": cc.criminal.crn, "first_name": cc.criminal.first_name, "last_name": cc.criminal.last_name}, "role": cc.role} for cc in case.criminals],
        "victims": [{"name": f"{v.first_name} {v.last_name}", "age": v.age, "gender": v.gender, "status": v.status, "injury_description": v.injury_description} for v in case.victims],
        "evidence": [{"evidence_number": e.evidence_number, "type": e.type, "description": e.description, "collected_by": e.collected_by, "status": e.status} for e in case.evidence],
    }
    xlsx = generate_case_excel(case_dict)
    create_audit_log(db, "CASE_REPORT_EXCEL_GENERATED", user_id=current_user.id,
                     username=current_user.username, role=current_user.role, resource_type="case", resource_id=case_id)
    return Response(content=xlsx, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=case_{case.case_number.replace('/', '_')}.xlsx"})
