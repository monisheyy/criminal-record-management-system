from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional
from datetime import datetime
from pathlib import Path
from app.database import get_db
from app import models, schemas
from app.security import (
    require_admin,
    require_officer_or_admin,
    require_any_role,
)
from app.utils.audit import create_audit_log, create_notification
from app.ml.pipeline import get_pipeline, CRMSMLPipeline, DatasetValidationError, CANDIDATES_DIR

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _officer_can_access_prediction(pred: models.AIPrediction, db: Session, current_user: models.User) -> bool:
    """Object-level authorization for AI predictions. Admins have global access.
    Officers may access predictions attached to cases assigned to them, or predictions
    for criminals linked to one of their assigned cases.
    """
    if current_user.role.value == "admin":
        return True
    if pred.case_id:
        case = db.query(models.Case).filter(models.Case.id == pred.case_id).first()
        return bool(case and case.assigned_officer_id == current_user.id)
    if pred.criminal_id:
        return db.query(models.CaseCriminal).join(
            models.Case, models.Case.id == models.CaseCriminal.case_id
        ).filter(
            models.CaseCriminal.criminal_id == pred.criminal_id,
            models.Case.assigned_officer_id == current_user.id,
        ).first() is not None
    return False



@router.post("/predict", response_model=schemas.AIPredictionOut)
async def run_prediction(
    data: schemas.PredictionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_officer_or_admin)
):
    criminal = None
    case = None
    criminal_data = {}

    if data.criminal_id:
        criminal = db.query(models.Criminal).filter(models.Criminal.id == data.criminal_id).first()
        if not criminal:
            raise HTTPException(status_code=404, detail="Criminal not found")
        if current_user.role.value == "investigating_officer":
            has_access = db.query(models.CaseCriminal).join(
                models.Case, models.Case.id == models.CaseCriminal.case_id
            ).filter(
                models.CaseCriminal.criminal_id == data.criminal_id,
                models.Case.assigned_officer_id == current_user.id,
            ).first() is not None
            if not has_access:
                raise HTTPException(status_code=403, detail="You are not authorized to assess this criminal")
        criminal_data = {
            "id": criminal.id,
            "first_name": criminal.first_name,
            "last_name": criminal.last_name,
            "prior_convictions": criminal.prior_convictions,
            "date_of_birth": str(criminal.date_of_birth) if criminal.date_of_birth else None,
            "crime_type": criminal.crime_type,
            "gang_id": criminal.gang_id,
            "is_wanted": criminal.is_wanted,
            "is_incarcerated": criminal.is_incarcerated,
            "known_associates": criminal.known_associates,
        }

    if data.case_id:
        case = db.query(models.Case).filter(models.Case.id == data.case_id).first()
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        if current_user.role.value == "investigating_officer" and case.assigned_officer_id != current_user.id:
            raise HTTPException(status_code=403, detail="You are not assigned to this case")
        if not criminal_data:
            criminal_data = {
                "crime_type": case.crime_type,
                "prior_convictions": None,
            }
        # The incident timestamp is an observed case field. It can support the
        # time-of-day feature without inferring any feature from the target label.
        if case.incident_date is not None:
            criminal_data["incident_date"] = case.incident_date.isoformat()

    pipeline = get_pipeline()
    try:
        result = pipeline.predict(criminal_data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DatasetValidationError as exc:
        raise HTTPException(status_code=503, detail=f"AI model dataset is invalid: {exc}") from exc

    # Find similar criminals
    all_criminals = db.query(models.Criminal).limit(200).all()
    all_criminal_dicts = [
        {"id": c.id, "first_name": c.first_name, "last_name": c.last_name,
         "prior_convictions": c.prior_convictions or 0,
         "crime_type": c.crime_type, "gang_id": c.gang_id,
         "is_wanted": c.is_wanted, "is_incarcerated": c.is_incarcerated,
         "date_of_birth": str(c.date_of_birth) if c.date_of_birth else None,
         "known_associates": c.known_associates}
        for c in all_criminals
    ]
    similar = pipeline.find_similar_criminals(criminal_data, all_criminal_dicts, top_k=5)
    explanation = (result.get("input_features") or {}).get("explanation", {})
    # Similar-record matching is kept separate from model feature importance:
    # similarity is retrieval context, not an explanation of model causality.

    # Resolve predicted gang id
    predicted_gang_id = None
    if result.get('predicted_gang'):
        gang = db.query(models.Gang).filter(models.Gang.name == result['predicted_gang']).first()
        predicted_gang_id = gang.id if gang else None
        if not predicted_gang_id:
            predicted_gang_id = criminal.gang_id if criminal else None

    prediction = models.AIPrediction(
    criminal_id=data.criminal_id,
    case_id=data.case_id,
    predicted_crime_type=result["predicted_crime_type"],
    crime_type_confidence=result["crime_type_confidence"] / 100.0,
    gang_affiliation_probability=result["gang_affiliation_probability"] / 100.0,
    predicted_gang_id=predicted_gang_id,
    risk_score=result["risk_score"],
    risk_level=result["risk_level"],
    confidence_overall=result["confidence_overall"] / 100.0,
    similar_criminals=similar,
    input_features=result.get("input_features"),
    model_version=pipeline.model_version,
)
    db.add(prediction)
    db.commit()
    db.refresh(prediction)

    # A model output is advisory only. Do not mutate the official criminal
    # risk/threat fields automatically; a qualified human must review it first.
    # High scores create review notifications, not an assertion of dangerousness.
    if result['risk_score'] >= 75:
        display_name = f"{criminal.first_name} {criminal.last_name}" if criminal else "Case review"
        create_notification(
            db,
            title=f"AI prediction requires review: {display_name}",
            message=(f"AI-generated prototype score: {result['risk_score']:.1f}/100. "
                     f"This is an unvalidated decision-support output, not a finding of dangerousness. "
                     f"Review prediction #{prediction.id} and its evidence before taking any action."),
            notification_type="warning",
            target_role="admin",
            related_criminal_id=data.criminal_id,
        )
        create_notification(
            db,
            title=f"AI prediction review requested: {display_name}",
            message=(f"Please review AI prediction #{prediction.id} and verify supporting evidence. "
                     "The model score must not independently determine official status or action."),
            notification_type="warning",
            target_role="investigating_officer",
            related_criminal_id=data.criminal_id,
        )

    create_audit_log(
        db, "AI_PREDICTION_RUN",
        user_id=current_user.id, username=current_user.username, role=current_user.role,
        resource_type="ai_prediction", resource_id=prediction.id,
        details={
            "criminal_id": data.criminal_id,
            "risk_score": result['risk_score'],
            "model_version": pipeline.model_version,
            "explanation_method": explanation.get("method"),
            "top_features": [item.get("feature") for item in explanation.get("top_features", [])],
        }
    )
    return prediction


@router.get("/predictions", response_model=List[schemas.AIPredictionOut])
async def list_predictions(
    criminal_id: Optional[int] = Query(None),
    case_id: Optional[int] = Query(None),
    review_status: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    q = db.query(models.AIPrediction)
    if criminal_id:
        q = q.filter(models.AIPrediction.criminal_id == criminal_id)
    if case_id:
        q = q.filter(models.AIPrediction.case_id == case_id)
    if review_status:
        q = q.filter(models.AIPrediction.review_status == review_status)
    if risk_level:
        q = q.filter(models.AIPrediction.risk_level == risk_level)
    if current_user.role.value == "investigating_officer":
        assigned_case_ids = db.query(models.Case.id).filter(
            models.Case.assigned_officer_id == current_user.id
        ).subquery()
        assigned_criminal_ids = db.query(models.CaseCriminal.criminal_id).join(
            models.Case, models.Case.id == models.CaseCriminal.case_id
        ).filter(models.Case.assigned_officer_id == current_user.id).subquery()
        q = q.filter(or_(
            models.AIPrediction.case_id.in_(assigned_case_ids),
            models.AIPrediction.criminal_id.in_(assigned_criminal_ids),
        ))
    return q.order_by(models.AIPrediction.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/predictions/{prediction_id}", response_model=schemas.AIPredictionOut)
async def get_prediction(
    prediction_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_officer_or_admin)
):
    pred = db.query(models.AIPrediction).filter(models.AIPrediction.id == prediction_id).first()
    if not pred:
        raise HTTPException(status_code=404, detail="Prediction not found")
    if current_user.role.value == "investigating_officer" and not _officer_can_access_prediction(pred, db, current_user):
        raise HTTPException(status_code=403, detail="You are not authorized to access this prediction")
    return pred


@router.post("/predictions/{prediction_id}/review", response_model=schemas.AIPredictionOut)
async def review_prediction(
    prediction_id: int,
    review: schemas.PredictionReview,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_officer_or_admin)
):
    pred = db.query(models.AIPrediction).filter(models.AIPrediction.id == prediction_id).first()
    if not pred:
        raise HTTPException(status_code=404, detail="Prediction not found")
    if current_user.role.value == "investigating_officer" and not _officer_can_access_prediction(pred, db, current_user):
        raise HTTPException(status_code=403, detail="You are not authorized to review this prediction")

    original_prediction = {"predicted_crime_type": pred.predicted_crime_type, "risk_score": pred.risk_score, "risk_level": pred.risk_level, "model_version": pred.model_version, "review_status": pred.review_status.value}
    pred.review_status = review.status
    pred.reviewed_by_id = current_user.id
    pred.reviewed_at = datetime.utcnow()
    pred.officer_remarks = review.remarks
    if review.override_crime_type:
        pred.override_crime_type = review.override_crime_type

    db.commit()
    db.refresh(pred)

    create_audit_log(
        db, f"AI_PREDICTION_{review.status.value.upper()}",
        user_id=current_user.id, username=current_user.username, role=current_user.role,
        resource_type="ai_prediction", resource_id=prediction_id,
        details={"status": review.status.value, "remarks": review.remarks}
    )
    return pred


@router.post("/retrain")
async def retrain_model(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    """Train and persist a candidate; never overwrite the active model here."""
    candidate = CRMSMLPipeline()
    try:
        metrics = candidate.train(save=False)
        candidate_path = candidate.save_candidate()
    except DatasetValidationError as exc:
        raise HTTPException(status_code=422, detail=f"ML dataset validation failed: {exc}") from exc
    except (FileNotFoundError, ValueError, OSError) as exc:
        raise HTTPException(status_code=500, detail="Candidate training failed. Check server logs for details.") from exc

    version = metrics["model_version"]
    crime_m = metrics["crime_classifier"]
    evaluation_metadata = {
        "crime_classifier": crime_m,
        "gang_predictor": metrics.get("gang_predictor", {}),
        "evaluation_method": metrics.get("evaluation_method"),
        "dataset_type": metrics.get("dataset", {}).get("dataset_type"),
        "dataset_version": metrics.get("dataset", {}).get("dataset_version"),
        "dataset_sha256": metrics.get("dataset", {}).get("sha256"),
        "candidate_path": str(Path(candidate_path).resolve()),
        "candidate_status": "awaiting_review",
    }
    ml_record = models.MLModel(
        version=version,
        model_type="crime_classifier",
        accuracy=crime_m["accuracy"],
        precision_score=crime_m["precision"],
        recall_score=crime_m["recall"],
        f1_score=crime_m["f1"],
        training_samples=crime_m["training_samples"],
        feature_importances=metrics.get("feature_importances"),
        evaluation_metadata=evaluation_metadata,
        dataset_version=metrics.get("dataset", {}).get("dataset_version", "unknown"),
        evaluation_method=metrics.get("evaluation_method"),
        is_active=False,
        notes=(f"Candidate trained by {current_user.full_name}; not activated. "
               f"dataset_type={metrics.get('dataset', {}).get('dataset_type', 'unknown')}"),
    )
    db.add(ml_record)
    db.commit()
    db.refresh(ml_record)
    create_audit_log(
        db, "MODEL_CANDIDATE_TRAINED",
        user_id=current_user.id, username=current_user.username,
        resource_type="ml_model", resource_id=ml_record.id,
        details={"version": version, "accuracy": crime_m["accuracy"], "candidate_status": "awaiting_review"},
    )
    return {
        "message": "Candidate trained and saved for review. The active model was not changed.",
        "model_id": ml_record.id,
        "version": version,
        "candidate_status": "awaiting_review",
        "active_model_unchanged": True,
        "metrics": metrics,
    }


@router.post("/models/{model_id}/activate")
async def activate_model_candidate(
    model_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Promote a reviewed candidate to active artifacts; admin-only operation."""
    record = db.query(models.MLModel).filter(models.MLModel.id == model_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Model candidate not found")
    metadata = record.evaluation_metadata or {}
    candidate_path = metadata.get("candidate_path")
    if metadata.get("candidate_status") != "awaiting_review" or not candidate_path:
        raise HTTPException(status_code=409, detail="This model is not an activatable candidate")
    if metadata.get("dataset_type") == "synthetic_demonstration":
        raise HTTPException(
            status_code=409,
            detail=("This candidate was trained on synthetic demonstration data and cannot be activated. "
                    "Use an authorized, quality-reviewed dataset and complete the evaluation process first."),
        )

    try:
        candidate_dir = Path(candidate_path).resolve()
        pipeline = get_pipeline()
        pipeline.activate_candidate(candidate_dir)
    except (ValueError, OSError, FileNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=f"Candidate activation failed: {exc}") from exc

    # Mark the candidate as active only after artifact activation and pipeline reload.
    db.query(models.MLModel).update({models.MLModel.is_active: False}, synchronize_session=False)
    record.is_active = True
    metadata["candidate_status"] = "active"
    record.evaluation_metadata = metadata
    db.commit()
    create_audit_log(
        db, "MODEL_CANDIDATE_ACTIVATED",
        user_id=current_user.id, username=current_user.username,
        resource_type="ml_model", resource_id=record.id,
        details={"version": record.version, "model_id": record.id},
    )
    return {"message": "Candidate activated", "model_id": record.id, "version": record.version, "active_model_version": pipeline.model_version}


@router.get("/models", response_model=List[schemas.MLModelOut])
async def list_models(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_officer_or_admin)
):
    return db.query(models.MLModel).order_by(models.MLModel.trained_at.desc()).all()
