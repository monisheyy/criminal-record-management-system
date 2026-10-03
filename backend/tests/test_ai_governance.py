"""Human review, quality gates, artifact integrity and demo-mode controls."""
import json
import random
import string

import numpy as np
import pytest

from app.ml import pipeline as ml


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def prediction(client, admin_token):
    criminal = client.post("/api/criminals", json={
        "first_name": "Governance", "last_name": "".join(random.choices(string.ascii_lowercase, k=8)).title(),
        "crime_type": "Robbery", "prior_convictions": 2,
    }, headers=_bearer(admin_token))
    assert criminal.status_code == 200, criminal.text
    r = client.post("/api/ai/predict", json={"criminal_id": criminal.json()["id"]}, headers=_bearer(admin_token))
    assert r.status_code == 200, r.text
    return r.json()


def test_prediction_carries_advisory_notice_provenance_and_fraction_units(prediction):
    assert "not evidence" in prediction["advisory_notice"]
    assert 0.0 <= prediction["crime_type_confidence"] <= 1.0
    assert 0.0 <= prediction["confidence_overall"] <= 1.0
    provenance = prediction["input_features"]["provenance"]
    assert provenance["criminal_record_id"] == prediction["criminal_id"]
    assert provenance["model_dataset_type"] == "synthetic_demonstration"
    assert "uncalibrated" in prediction["input_features"]["calibration_warning"]


@pytest.mark.parametrize("payload", [
    {"status": "confirmed"},                                                  # no reason
    {"status": "confirmed", "remarks": "ok"},                                 # too short
    {"status": "overridden", "remarks": "Field intelligence says otherwise"},  # missing override type
    {"status": "confirmed", "remarks": "Looks right to me overall", "override_crime_type": "Fraud"},
    {"status": "overridden", "remarks": "Field intelligence says otherwise", "override_crime_type": "Jaywalking"},
    {"status": "pending", "remarks": "Resetting this to pending"},
])
def test_review_requires_documented_reasoning(client, admin_token, prediction, payload):
    r = client.post(f"/api/ai/predictions/{prediction['id']}/review", json=payload, headers=_bearer(admin_token))
    assert r.status_code == 422, r.text


def test_review_history_is_append_only_and_records_corrections(client, admin_token, prediction):
    url = f"/api/ai/predictions/{prediction['id']}/review"
    first = client.post(url, json={"status": "confirmed", "remarks": "Matches the arrest record on file"},
                        headers=_bearer(admin_token))
    assert first.status_code == 200
    second = client.post(url, json={"status": "overridden", "remarks": "New forensic report changes the picture",
                                    "override_crime_type": "Fraud"}, headers=_bearer(admin_token))
    assert second.status_code == 200
    body = second.json()
    assert body["review_status"] == "overridden" and body["override_crime_type"] == "Fraud"
    assert [r["decision"] for r in body["reviews"]] == ["confirmed", "overridden"]
    assert body["reviews"][1]["previous_status"] == "confirmed"
    logs = client.get("/api/admin/audit-logs", params={"action": "AI_PREDICTION_OVERRIDDEN_CORRECTED"},
                      headers=_bearer(admin_token)).json()
    assert any(log["resource_id"] == prediction["id"] for log in logs)


def test_review_history_rows_cannot_be_modified(prediction, client, admin_token):
    from app import models
    from app.database import SessionLocal

    client.post(f"/api/ai/predictions/{prediction['id']}/review",
                json={"status": "rejected", "remarks": "Insufficient corroborating evidence"}, headers=_bearer(admin_token))
    db = SessionLocal()
    try:
        row = db.query(models.AIPredictionReview).filter_by(prediction_id=prediction["id"]).first()
        row.remarks = "rewritten history"
        with pytest.raises(PermissionError):
            db.commit()
    finally:
        db.rollback()
        db.close()


def test_predictions_disabled_for_synthetic_model_when_not_allowed(client, admin_token, monkeypatch, prediction):
    from dataclasses import replace
    from app.routers import ai_predictions

    monkeypatch.setattr(ai_predictions, "settings", replace(ai_predictions.settings, ai_allow_synthetic_models=False))
    r = client.post("/api/ai/predict", json={"criminal_id": prediction["criminal_id"]}, headers=_bearer(admin_token))
    assert r.status_code == 503
    status = client.get("/api/ai/status", headers=_bearer(admin_token)).json()
    assert status["predictions_enabled"] is False and status["mode"] == "demo"


def test_training_reports_calibration_subgroups_and_quality_gate():
    metrics = ml.CRMSMLPipeline().train(save=False)
    crime = metrics["crime_classifier"]
    calibration = crime["calibration"]
    assert 0.0 <= calibration["expected_calibration_error"] <= 1.0
    assert calibration["brier_score"] >= 0.0
    assert sum(b["count"] for b in calibration["reliability_table"]) == crime["test_samples"]
    slices = crime["subgroup_evaluation"]["slices"]
    # Operational slices plus the dataset's own slice_* columns (slice_state).
    assert set(slices) == set(ml.SUBGROUP_SLICES) | {"state"}
    for groups in slices.values():
        assert sum(g["n"] for g in groups) <= crime["test_samples"]
    gate = metrics["quality_gate"]
    assert {c["check"] for c in gate["checks"]} >= {"macro_f1", "balanced_accuracy", "expected_calibration_error"}
    assert gate["passed"] == all(c["passed"] for c in gate["checks"])


def test_quality_gate_fails_on_poor_metrics():
    poor = {"macro_f1": 0.1, "balanced_accuracy": 0.1, "zero_recall_classes": ["Arson"], "test_samples": 5,
            "beats_majority_baseline": False, "calibration": {"expected_calibration_error": 0.5}}
    gate = ml.evaluate_quality_gate(poor, {"min_macro_f1": 0.6, "min_balanced_accuracy": 0.6,
                                           "max_zero_recall_classes": 0, "min_test_samples": 100,
                                           "max_expected_calibration_error": 0.15,
                                           "require_beats_majority_baseline": True})
    assert gate["passed"] is False
    assert all(not c["passed"] for c in gate["checks"])


def test_ece_is_zero_for_perfectly_calibrated_confident_model():
    y = np.array([0, 1, 2, 1])
    proba = np.eye(3)[y]
    assert ml.expected_calibration_error(y, proba)["expected_calibration_error"] == 0.0


def test_tampered_artifact_is_refused_before_unpickling(tmp_path):
    trained = ml.CRMSMLPipeline()
    trained.train(save=False)
    trained._save_models(tmp_path)
    metadata = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    assert ml.verify_artifacts(tmp_path, metadata)["verified"] is True

    with (tmp_path / "encoders.pkl").open("ab") as handle:
        handle.write(b"tampered")
    with pytest.raises(ml.ArtifactIntegrityError, match="hash mismatch"):
        ml.verify_artifacts(tmp_path, metadata)


def test_forged_hashes_without_secret_fail_signature_check(tmp_path):
    trained = ml.CRMSMLPipeline()
    trained.train(save=False)
    trained._save_models(tmp_path)
    with (tmp_path / "encoders.pkl").open("ab") as handle:
        handle.write(b"tampered")
    metadata = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    metadata["artifact_sha256"]["encoders.pkl"] = ml._file_sha256(tmp_path / "encoders.pkl")  # attacker rewrites hash
    with pytest.raises(ml.ArtifactIntegrityError, match="signature"):
        ml.verify_artifacts(tmp_path, metadata)


def test_activation_requires_justification_and_blocks_synthetic(client, admin_token):
    trained = client.post("/api/ai/retrain", headers=_bearer(admin_token))
    assert trained.status_code == 200, trained.text
    model_id = trained.json()["model_id"]
    assert "quality_gate" in trained.json()
    no_reason = client.post(f"/api/ai/models/{model_id}/activate", json={}, headers=_bearer(admin_token))
    assert no_reason.status_code == 422
    synthetic = client.post(f"/api/ai/models/{model_id}/activate",
                            json={"justification": "Reviewed metrics with the model owner and approved"},
                            headers=_bearer(admin_token))
    assert synthetic.status_code == 409
    assert "synthetic" in synthetic.json()["detail"]


def test_activation_blocked_when_quality_gate_failed(client, admin_token):
    from app import models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        record = models.MLModel(version="vtest-gate", model_type="crime_classifier", is_active=False,
                                evaluation_metadata={"candidate_status": "awaiting_review",
                                                     "candidate_path": str(ml.CANDIDATES_DIR / "x"),
                                                     "dataset_type": "authorized_real",
                                                     "quality_gate": {"passed": False, "checks": [
                                                         {"check": "macro_f1", "passed": False}]}})
        db.add(record)
        db.commit()
        model_id = record.id
    finally:
        db.close()
    r = client.post(f"/api/ai/models/{model_id}/activate",
                    json={"justification": "Attempting to activate a failing candidate"}, headers=_bearer(admin_token))
    assert r.status_code == 409
    assert "quality gate" in r.json()["detail"]
