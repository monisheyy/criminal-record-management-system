from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.constants import AI_ADVISORY_NOTICE
from app.database import get_db
from app import models, schemas
from app.security import require_admin, require_officer_or_admin
from app.utils.audit import create_audit_log, create_notification
from app.utils.pagination import MAX_PAGE_SIZE, paginate
from app.ml.pipeline import (
    ArtifactIntegrityError, CANDIDATES_DIR, CRMSMLPipeline, DatasetValidationError,
    evaluate_quality_gate, get_pipeline,
)

router = APIRouter(prefix="/api/ai", tags=["ai"])

HIGH_SCORE_REVIEW_THRESHOLD = 75


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


def _with_notice(pred: models.AIPrediction) -> models.AIPrediction:
    pred.advisory_notice = AI_ADVISORY_NOTICE
    return pred


def _load_pipeline() -> CRMSMLPipeline:
    try:
        return get_pipeline()
    except ArtifactIntegrityError as exc:
        raise HTTPException(status_code=503, detail=f"AI model failed integrity verification: {exc}") from exc


def _ensure_predictions_allowed(pipeline: CRMSMLPipeline) -> None:
    if not settings.ai_predictions_enabled:
        raise HTTPException(status_code=503, detail="AI predictions are disabled by configuration (AI_PREDICTIONS_ENABLED=false)")
    if pipeline.is_synthetic and not settings.ai_allow_synthetic_models:
        raise HTTPException(
            status_code=503,
            detail="The loaded model was trained on synthetic/unvalidated data and is disabled in this environment.",
        )


@router.get("/status")
async def ai_status(current_user: models.User = Depends(require_officer_or_admin)):
    """Operating mode of the AI subsystem, used by the UI to label outputs."""
    try:
        pipeline = get_pipeline()
    except ArtifactIntegrityError as exc:
        return {"predictions_enabled": False, "mode": "disabled", "reason": str(exc), "advisory_notice": AI_ADVISORY_NOTICE}
    gate = pipeline.training_metadata.get("quality_gate")
    enabled = settings.ai_predictions_enabled and (not pipeline.is_synthetic or settings.ai_allow_synthetic_models)
    return {
        "predictions_enabled": enabled,
        "mode": "demo" if pipeline.is_synthetic else "validated-candidate",
        "model_version": pipeline.model_version,
        "dataset_type": pipeline.dataset_type,
        "artifact_integrity": pipeline.integrity.get("status"),
        "quality_gate_passed": gate.get("passed") if isinstance(gate, dict) else None,
        "advisory_notice": AI_ADVISORY_NOTICE,
    }


@router.post("/predict", response_model=schemas.AIPredictionOut)
async def run_prediction(
    data: schemas.PredictionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_officer_or_admin)
):
    pipeline = _load_pipeline()
    _ensure_predictions_allowed(pipeline)

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
        if criminal and not any(cc.criminal_id == criminal.id for cc in case.criminals):
            raise HTTPException(status_code=422, detail="The criminal is not linked to this case")
        if not criminal_data:
            criminal_data = {
                "crime_type": case.crime_type if case.crime_type not in ("Other", "Unclassified") else None,
                "prior_convictions": None,
            }
        # The incident timestamp is an observed case field. It can support the
        # time-of-day feature without inferring any feature from the target label.
        if case.incident_date is not None:
            criminal_data["incident_date"] = case.incident_date.isoformat()

    try:
        result = pipeline.predict(criminal_data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DatasetValidationError as exc:
        raise HTTPException(status_code=503, detail=f"AI model dataset is invalid: {exc}") from exc

    # Similar-record retrieval is context for the reviewer, not model causality.
    candidates = db.query(models.Criminal).order_by(models.Criminal.id.desc()).limit(500).all()
    all_criminal_dicts = [
        {"id": c.id, "first_name": c.first_name, "last_name": c.last_name,
         "prior_convictions": c.prior_convictions or 0,
         "crime_type": c.crime_type, "gang_id": c.gang_id,
         "is_wanted": c.is_wanted, "is_incarcerated": c.is_incarcerated,
         "date_of_birth": str(c.date_of_birth) if c.date_of_birth else None,
         "known_associates": c.known_associates}
        for c in candidates
    ]
    similar = pipeline.find_similar_criminals(criminal_data, all_criminal_dicts, top_k=5)
    explanation = (result.get("input_features") or {}).get("explanation", {})

    predicted_gang_id = None
    if result.get('predicted_gang'):
        gang = db.query(models.Gang).filter(models.Gang.name == result['predicted_gang']).first()
        predicted_gang_id = gang.id if gang else None

    input_features = dict(result.get("input_features") or {})
    input_features["provenance"] = {
        "criminal_record_id": data.criminal_id,
        "case_id": data.case_id,
        "record_last_updated": (criminal.updated_at or criminal.created_at).isoformat() if criminal and (criminal.updated_at or criminal.created_at) else None,
        "generated_by_user_id": current_user.id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_dataset_type": pipeline.dataset_type,
    }

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
        input_features=input_features,
        model_version=pipeline.model_version,
    )
    db.add(prediction)
    db.flush()
    create_audit_log(
        db, "AI_PREDICTION_RUN", actor=current_user,
        resource_type="ai_prediction", resource_id=prediction.id,
        details={
            "criminal_id": data.criminal_id,
            "case_id": data.case_id,
            "risk_score": result['risk_score'],
            "model_version": pipeline.model_version,
            "dataset_type": pipeline.dataset_type,
            "explanation_method": explanation.get("method"),
            "top_features": [item.get("feature") for item in explanation.get("top_features", [])],
        },
        commit=False,
    )
    db.commit()
    db.refresh(prediction)

    # A model output is advisory only. Official risk/threat fields are never
    # changed automatically; high scores only request a human review.
    if result['risk_score'] >= HIGH_SCORE_REVIEW_THRESHOLD:
        display_name = f"{criminal.first_name} {criminal.last_name}" if criminal else "Case review"
        subject_key = f"criminal:{data.criminal_id}" if data.criminal_id else f"case:{data.case_id}"
        create_notification(
            db,
            title=f"AI prediction requires review: {display_name}",
            message=(f"AI-generated prototype score: {result['risk_score']:.1f}/100. "
                     f"This is an unvalidated decision-support output, not a finding of dangerousness. "
                     f"Review prediction #{prediction.id} and its evidence before taking any action."),
            notification_type="warning",
            target_role="admin",
            related_criminal_id=data.criminal_id,
            related_case_id=data.case_id,
            dedup_key=f"ai-review:{subject_key}",
        )
        assigned_officer_id = case.assigned_officer_id if case else None
        create_notification(
            db,
            title=f"AI prediction review requested: {display_name}",
            message=(f"Please review AI prediction #{prediction.id} and verify supporting evidence. "
                     "The model score must not independently determine official status or action."),
            notification_type="warning",
            target_role=None if assigned_officer_id else "investigating_officer",
            target_user_id=assigned_officer_id,
            related_criminal_id=data.criminal_id,
            related_case_id=data.case_id,
            dedup_key=f"ai-review:{subject_key}",
        )
    return _with_notice(prediction)


@router.get("/predictions", response_model=List[schemas.AIPredictionOut])
async def list_predictions(
    response: Response,
    criminal_id: Optional[int] = Query(None, ge=1),
    case_id: Optional[int] = Query(None, ge=1),
    review_status: Optional[schemas.PredictionStatus] = Query(None),
    risk_level: Optional[schemas.ThreatLevel] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_officer_or_admin)
):
    q = db.query(models.AIPrediction).options(
        selectinload(models.AIPrediction.reviews), selectinload(models.AIPrediction.criminal)
    )
    if criminal_id:
        q = q.filter(models.AIPrediction.criminal_id == criminal_id)
    if case_id:
        q = q.filter(models.AIPrediction.case_id == case_id)
    if review_status:
        q = q.filter(models.AIPrediction.review_status == review_status.value)
    if risk_level:
        q = q.filter(models.AIPrediction.risk_level == risk_level.value)
    if current_user.role.value == "investigating_officer":
        assigned_case_ids = db.query(models.Case.id).filter(
            models.Case.assigned_officer_id == current_user.id
        )
        assigned_criminal_ids = db.query(models.CaseCriminal.criminal_id).join(
            models.Case, models.Case.id == models.CaseCriminal.case_id
        ).filter(models.Case.assigned_officer_id == current_user.id)
        q = q.filter(or_(
            models.AIPrediction.case_id.in_(assigned_case_ids),
            models.AIPrediction.criminal_id.in_(assigned_criminal_ids),
        ))
    q = q.order_by(models.AIPrediction.created_at.desc(), models.AIPrediction.id.desc())
    return [_with_notice(p) for p in paginate(q, response, skip, limit)]


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
    return _with_notice(pred)


@router.post("/predictions/{prediction_id}/review", response_model=schemas.AIPredictionOut)
async def review_prediction(
    prediction_id: int,
    review: schemas.PredictionReview,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_officer_or_admin)
):
    """Record a human decision. Every decision (including later corrections)
    is appended to the review history with the reviewer's stated reasons."""
    pred = db.query(models.AIPrediction).filter(models.AIPrediction.id == prediction_id).first()
    if not pred:
        raise HTTPException(status_code=404, detail="Prediction not found")
    if current_user.role.value == "investigating_officer" and not _officer_can_access_prediction(pred, db, current_user):
        raise HTTPException(status_code=403, detail="You are not authorized to review this prediction")

    previous_status = pred.review_status.value
    is_correction = previous_status != "pending"
    original_prediction = {"predicted_crime_type": pred.predicted_crime_type, "risk_score": pred.risk_score,
                           "risk_level": pred.risk_level, "model_version": pred.model_version,
                           "review_status": previous_status}

    pred.review_status = models.PredictionStatus(review.status)
    pred.reviewed_by_id = current_user.id
    pred.reviewed_at = datetime.now(timezone.utc)
    pred.officer_remarks = review.remarks
    pred.override_crime_type = review.override_crime_type if review.status == "overridden" else None
    db.add(models.AIPredictionReview(
        prediction_id=pred.id,
        reviewer_id=current_user.id,
        reviewer_username=current_user.username,
        previous_status=previous_status,
        decision=review.status,
        remarks=review.remarks,
        override_crime_type=pred.override_crime_type,
    ))
    create_audit_log(
        db, f"AI_PREDICTION_{review.status.upper()}" + ("_CORRECTED" if is_correction else ""),
        actor=current_user, resource_type="ai_prediction", resource_id=prediction_id,
        reason=review.remarks,
        details={"status": review.status, "previous_status": previous_status,
                 "override_crime_type": pred.override_crime_type, "original_prediction": original_prediction},
        commit=False,
    )
    db.commit()
    db.refresh(pred)
    return _with_notice(pred)


@router.post("/retrain")
async def retrain_model(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin)
):
    """Train and persist a candidate; never overwrite the active model here."""
    try:
        candidate = CRMSMLPipeline()  # loads current artifacts first (integrity-checked)
    except ArtifactIntegrityError as exc:
        raise HTTPException(status_code=503, detail=f"Active model failed integrity verification: {exc}") from exc
    try:
        metrics = candidate.train(save=False)
        candidate_path = candidate.save_candidate()
    except DatasetValidationError as exc:
        raise HTTPException(status_code=422, detail=f"ML dataset validation failed: {exc}") from exc
    except (FileNotFoundError, ValueError, OSError) as exc:
        raise HTTPException(status_code=500, detail="Candidate training failed. Check server logs for details.") from exc

    version = metrics["model_version"]
    crime_m = metrics["crime_classifier"]
    gate = metrics.get("quality_gate") or evaluate_quality_gate(crime_m)
    evaluation_metadata = {
        "crime_classifier": crime_m,
        "gang_predictor": metrics.get("gang_predictor", {}),
        "evaluation_method": metrics.get("evaluation_method"),
        "dataset_type": metrics.get("dataset", {}).get("dataset_type"),
        "dataset_version": metrics.get("dataset", {}).get("dataset_version"),
        "dataset_sha256": metrics.get("dataset", {}).get("sha256"),
        "candidate_path": str(Path(candidate_path).resolve()),
        "candidate_status": "awaiting_review",
        "quality_gate": gate,
        "artifact_sha256": candidate.training_metadata.get("artifact_sha256"),
        "trained_by_user_id": current_user.id,
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
               f"dataset_type={metrics.get('dataset', {}).get('dataset_type', 'unknown')}; "
               f"quality_gate={'passed' if gate.get('passed') else 'FAILED'}"),
    )
    db.add(ml_record)
    db.flush()
    create_audit_log(
        db, "MODEL_CANDIDATE_TRAINED", actor=current_user,
        resource_type="ml_model", resource_id=ml_record.id,
        details={"version": version, "accuracy": crime_m["accuracy"], "macro_f1": crime_m.get("macro_f1"),
                 "quality_gate_passed": gate.get("passed"), "candidate_status": "awaiting_review"},
        commit=False,
    )
    db.commit()
    db.refresh(ml_record)
    return {
        "message": "Candidate trained and saved for review. The active model was not changed.",
        "model_id": ml_record.id,
        "version": version,
        "candidate_status": "awaiting_review",
        "active_model_unchanged": True,
        "quality_gate": gate,
        "metrics": metrics,
    }


def _activate(record: models.MLModel, justification: str, db: Session, current_user: models.User, action: str):
    metadata = dict(record.evaluation_metadata or {})
    candidate_path = metadata.get("candidate_path")
    if metadata.get("candidate_status") not in {"awaiting_review", "retired"} or not candidate_path:
        raise HTTPException(status_code=409, detail="This model is not an activatable candidate")
    if metadata.get("dataset_type") == "synthetic_demonstration":
        raise HTTPException(
            status_code=409,
            detail=("This candidate was trained on synthetic demonstration data and cannot be activated. "
                    "Use an authorized, quality-reviewed dataset and complete the evaluation process first."),
        )
    gate = metadata.get("quality_gate") or evaluate_quality_gate(metadata.get("crime_classifier") or {})
    if not gate.get("passed"):
        failed = [c["check"] for c in gate.get("checks", []) if not c.get("passed")]
        raise HTTPException(status_code=409, detail=f"Candidate failed the release quality gate: {', '.join(failed) or 'unknown'}")

    try:
        candidate_dir = Path(candidate_path).resolve()
        if CANDIDATES_DIR.resolve() not in candidate_dir.parents:
            raise ValueError("Candidate path is outside the model candidates directory")
        pipeline = _load_pipeline()
        pipeline.activate_candidate(candidate_dir)
    except (ValueError, OSError, FileNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=f"Candidate activation failed: {exc}") from exc

    previous = db.query(models.MLModel).filter(models.MLModel.is_active.is_(True), models.MLModel.id != record.id).all()
    for old in previous:
        old.is_active = False
        old_meta = dict(old.evaluation_metadata or {})
        if old_meta.get("candidate_status") == "active":
            old_meta["candidate_status"] = "retired"
            old.evaluation_metadata = old_meta
    record.is_active = True
    record.activated_at = datetime.now(timezone.utc)
    record.activated_by_id = current_user.id
    metadata["candidate_status"] = "active"
    metadata["activation_justification"] = justification
    record.evaluation_metadata = metadata
    create_audit_log(
        db, action, actor=current_user, resource_type="ml_model", resource_id=record.id,
        reason=justification,
        details={"version": record.version, "model_id": record.id, "previous_active_ids": [m.id for m in previous]},
        commit=False,
    )
    db.commit()
    return {"message": "Candidate activated", "model_id": record.id, "version": record.version,
            "active_model_version": pipeline.model_version}


@router.post("/models/{model_id}/activate")
async def activate_model_candidate(
    model_id: int,
    body: schemas.ModelActivationRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Promote a reviewed candidate to active artifacts; admin-only, gated, justified."""
    record = db.query(models.MLModel).filter(models.MLModel.id == model_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Model candidate not found")
    return _activate(record, body.justification, db, current_user, "MODEL_CANDIDATE_ACTIVATED")


@router.post("/models/{model_id}/rollback")
async def rollback_model(
    model_id: int,
    body: schemas.ModelRollbackRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """Re-activate a previously active (retired) model version."""
    record = db.query(models.MLModel).filter(models.MLModel.id == model_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Model not found")
    if (record.evaluation_metadata or {}).get("candidate_status") != "retired":
        raise HTTPException(status_code=409, detail="Only a previously active (retired) model can be rolled back to")
    return _activate(record, body.justification, db, current_user, "MODEL_ROLLED_BACK")


@router.get("/models", response_model=List[schemas.MLModelOut])
async def list_models(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_officer_or_admin)
):
    return db.query(models.MLModel).order_by(models.MLModel.trained_at.desc(), models.MLModel.id.desc()).all()
