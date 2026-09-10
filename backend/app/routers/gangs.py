from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app import models, schemas
from app.security import require_any_role, require_admin
from app.utils.audit import create_audit_log

router = APIRouter(prefix="/api/gangs", tags=["gangs"])


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
    existing = db.query(models.Gang).filter(models.Gang.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Gang with this name already exists")
    gang = models.Gang(**data.model_dump())
    db.add(gang)
    db.commit()
    db.refresh(gang)
    create_audit_log(db, "GANG_CREATED", user_id=current_user.id, username=current_user.username,
                     resource_type="gang", resource_id=gang.id, details={"name": data.name})
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
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(gang, k, v)
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
    db.delete(gang)
    db.commit()
    return {"message": "Gang deleted"}
