from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from app.database import get_db
from app import models, schemas
from app.security import get_current_user, require_any_role, require_officer_or_admin
from app.utils.audit import create_audit_log, create_notification
from app.ml.pipeline import get_pipeline

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/predict", response_model=schemas.AIPredictionOut)
async def run_prediction(
    data: schemas.PredictionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    criminal = None
    case = None
    criminal_data = {}

    if data.criminal_id:
        criminal = db.query(models.Criminal).filter(models.Criminal.id == data.criminal_id).first()
        if not criminal:
            raise HTTPException(status_code=404, detail="Criminal not found")
        criminal_data = {
            "id": criminal.id,
            "first_name": criminal.first_name,
            "last_name": criminal.last_name,
            "prior_convictions": criminal.prior_convictions or 0,
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
        if not criminal_data:
            criminal_data = {
                "crime_type": case.crime_type,
                "prior_convictions": 0,
            }

    pipeline = get_pipeline()
    result = pipeline.predict(criminal_data)

    # Find similar criminals
    all_criminals = db.query(models.Criminal).limit(200).all()
    all_criminal_dicts = [
        {"id": c.id, "first_name": c.first_name, "last_name": c.last_name,
         "prior_convictions": c.prior_convictions or 0,
         "crime_type": c.crime_type, "gang_id": c.gang_id,
         "is_wanted": c.is_wanted, "date_of_birth": str(c.date_of_birth) if c.date_of_birth else None,
         "known_associates": c.known_associates}
        for c in all_criminals
    ]
    similar = pipeline.find_similar_criminals(criminal_data, all_criminal_dicts, top_k=5)

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
        predicted_crime_type=result['predicted_crime_type'],
        crime_type_confidence=result['crime_type_confidence'],
        gang_affiliation_probability=result['gang_affiliation_probability'],
        predicted_gang_id=predicted_gang_id,
        risk_score=result['risk_score'],
        risk_level=result['risk_level'],
        confidence_overall=result['confidence_overall'],
        similar_criminals=similar,
        input_features=result.get('input_features'),
        model_version="v1.0",
    )
    db.add(prediction)
    db.commit()
    db.refresh(prediction)

    # Update criminal risk score
    if criminal:
        criminal.risk_score = result['risk_score']
        if result['risk_level'] in ['high', 'critical']:
            criminal.threat_level = result['risk_level']
        db.commit()

    # High-risk alert
    if result['risk_score'] >= 75:
        create_notification(
            db,
            title=f"🚨 HIGH-RISK ALERT: {criminal.first_name + ' ' + criminal.last_name if criminal else 'Unknown'}",
            message=f"Risk score: {result['risk_score']:.1f}/100 — {result['risk_level'].upper()}. Immediate review required.",
            notification_type="alert",
            target_role="admin",
            related_criminal_id=data.criminal_id,
        )
        create_notification(
            db,
            title=f"🚨 HIGH-RISK: {criminal.first_name + ' ' + criminal.last_name if criminal else 'Unknown'}",
            message=f"Risk score: {result['risk_score']:.1f}/100. Please review AI prediction #{prediction.id}.",
            notification_type="alert",
            target_role="investigating_officer",
            related_criminal_id=data.criminal_id,
        )

    create_audit_log(
        db, "AI_PREDICTION_RUN",
        user_id=current_user.id, username=current_user.username,
        resource_type="ai_prediction", resource_id=prediction.id,
        details={"criminal_id": data.criminal_id, "risk_score": result['risk_score']}
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
    return q.order_by(models.AIPrediction.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/predictions/{prediction_id}", response_model=schemas.AIPredictionOut)
async def get_prediction(
    prediction_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    pred = db.query(models.AIPrediction).filter(models.AIPrediction.id == prediction_id).first()
    if not pred:
        raise HTTPException(status_code=404, detail="Prediction not found")
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
        user_id=current_user.id, username=current_user.username,
        resource_type="ai_prediction", resource_id=prediction_id,
        details={"status": review.status.value, "remarks": review.remarks}
    )
    return pred


@router.post("/retrain")
async def retrain_model(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_officer_or_admin)
):
    if current_user.role.value != "admin":
        raise HTTPException(status_code=403, detail="Only admins can retrain the model")

    pipeline = get_pipeline()
    metrics = pipeline.train()

    # Save model version record
    from datetime import datetime
    version = f"v{datetime.utcnow().strftime('%Y%m%d%H%M')}"
    crime_m = metrics['crime_classifier']
    ml_record = models.MLModel(
        version=version,
        model_type="crime_classifier",
        accuracy=crime_m['accuracy'],
        precision_score=crime_m['precision'],
        recall_score=crime_m['recall'],
        f1_score=crime_m['f1'],
        training_samples=crime_m['training_samples'],
        feature_importances=metrics.get('feature_importances'),
        notes=f"Retrained by {current_user.full_name}",
    )
    db.add(ml_record)
    db.commit()

    create_audit_log(
        db, "MODEL_RETRAINED",
        user_id=current_user.id, username=current_user.username,
        resource_type="ml_model", resource_id=ml_record.id,
        details={"version": version, "accuracy": crime_m['accuracy']}
    )
    return {"message": "Model retrained successfully", "version": version, "metrics": metrics}


@router.get("/models", response_model=List[schemas.MLModelOut])
async def list_models(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_any_role)
):
    return db.query(models.MLModel).order_by(models.MLModel.trained_at.desc()).all()
