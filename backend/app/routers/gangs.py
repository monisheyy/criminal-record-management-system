from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import require_any_role, require_admin
from app.utils.audit import create_audit_log

router = APIRouter(prefix="/api/gangs", tags=["gangs"])


def _name_taken(db: Session, name: str, exclude_id: int = None) -> bool:
    q = db.query(models.Gang.id).filter(func.lower(models.Gang.name) == name.lower())
    if exclude_id is not None:
        q = q.filter(models.Gang.id != exclude_id)
    return q.first() is not None


@router.get("", response_model=List[schemas.GangOut])
async def list_gangs(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    return db.query(models.Gang).order_by(models.Gang.name).all()


@router.post("", response_model=schemas.GangOut)
async def create_gang(
    data: schemas.GangCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    if _name_taken(db, data.name):
        raise HTTPException(status_code=409, detail="Gang with this name already exists")
    payload = data.model_dump()
    payload["threat_level"] = data.threat_level.value
    gang = models.Gang(**payload)
    db.add(gang)
    db.flush()
    create_audit_log(db, "GANG_CREATED", actor=current_user, resource_type="gang", resource_id=gang.id,
                     details={"name": data.name}, commit=False)
    db.commit()
    db.refresh(gang)
    return gang


@router.put("/{gang_id}", response_model=schemas.GangOut)
async def update_gang(
    gang_id: int,
    data: schemas.GangUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    gang = db.query(models.Gang).filter(models.Gang.id == gang_id).first()
    if not gang:
        raise HTTPException(status_code=404, detail="Gang not found")
    changes = data.model_dump(exclude_unset=True)
    if changes.get("name") and _name_taken(db, changes["name"], exclude_id=gang_id):
        raise HTTPException(status_code=409, detail="Gang with this name already exists")
    if changes.get("threat_level") is not None:
        changes["threat_level"] = changes["threat_level"].value
    before = {k: getattr(gang, k) for k in changes}
    for k, v in changes.items():
        setattr(gang, k, v)
    create_audit_log(db, "GANG_UPDATED", actor=current_user, resource_type="gang", resource_id=gang_id,
                     details={"before": before, "after": changes}, commit=False)
    db.commit()
    db.refresh(gang)
    return gang


@router.delete("/{gang_id}")
async def delete_gang(
    gang_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    gang = db.query(models.Gang).filter(models.Gang.id == gang_id).first()
    if not gang:
        raise HTTPException(status_code=404, detail="Gang not found")
    members = db.query(models.Criminal.id).filter(models.Criminal.gang_id == gang_id).count()
    if members:
        raise HTTPException(status_code=409, detail=f"{members} criminal record(s) reference this gang; reassign them or mark the gang inactive instead.")
    if db.query(models.AIPrediction.id).filter(models.AIPrediction.predicted_gang_id == gang_id).first():
        raise HTTPException(status_code=409, detail="AI predictions reference this gang; mark it inactive instead of deleting it.")
    name = gang.name
    db.delete(gang)
    create_audit_log(db, "GANG_DELETED", actor=current_user, resource_type="gang", resource_id=gang_id,
                     details={"name": name}, commit=False)
    db.commit()
    return {"message": "Gang deleted"}
