"""The bundled India demo dataset and the learned danger score."""
import math

import numpy as np

from app.constants import CRIME_TYPES, GANG_NAMES
from app.ml import pipeline as ml
from app.ml.data import generate_india_dataset as gen


def test_dataset_is_reproducible_and_covers_every_class():
    assert gen.generate_rows(50) == gen.generate_rows(50)
    _, y_crime, y_gang, meta, context = ml.load_training_dataset(with_context=True)
    assert meta["dataset_type"] == "synthetic_demonstration"  # can never back an activated model
    assert meta["has_outcome"] and 0.2 < meta["outcome_rate"] < 0.6
    assert set(y_crime) == set(CRIME_TYPES)
    assert set(y_gang) == set(GANG_NAMES) | {"None"}
    assert min(meta["crime_class_counts"].values()) >= 100
    assert set(context["slices"]) == {"state"}


def test_models_learn_the_patterns_in_the_data():
    meta = ml.CRMSMLPipeline().get_metadata()
    crime, gang, risk = meta["crime_classifier"], meta["gang_predictor"], meta["risk_model"]
    assert meta["holdout_split"] == "time"
    assert crime["accuracy"] > 3 * crime["majority_baseline_accuracy"]
    assert crime["zero_recall_classes"] == []
    assert gang["balanced_accuracy"] > 0.5  # 7 classes: chance is about 0.14
    assert risk["roc_auc"] > 0.7
    assert risk["calibration"]["expected_calibration_error"] < 0.05
    rates = [risk["level_outcome_rates"][level]["observed_rate"] for level in ("low", "medium", "high", "critical")]
    assert rates == sorted(rates), "higher danger levels must have higher observed re-arrest rates"


def test_learned_danger_score_is_exactly_explained_by_its_factors():
    pipeline = ml.CRMSMLPipeline()
    result = pipeline.predict({"prior_convictions": 6, "date_of_birth": "2002-01-01", "gang_id": 1,
                               "weapons_involved": 1, "incident_date": "2024-02-01T23:30:00"})
    inputs = result["input_features"]
    assert inputs["risk_score_method"]["type"] == "learned_logistic_regression"
    probability = (result["risk_score"] - 1.0) / 99.0
    logit = math.log(probability / (1.0 - probability))
    intercept = float(pipeline.risk_model.named_steps["model"].intercept_[0])
    total = intercept + sum(factor["contribution"] for factor in inputs["risk_factors"])
    assert abs(total - logit) < 0.05  # contributions are rounded to 3 decimals
    unrecorded = {f["key"] for f in inputs["risk_factors"] if f["imputed"]}
    assert "violence_history" in unrecorded and "prior_convictions" not in unrecorded


def test_more_priors_mean_a_higher_danger_score():
    pipeline = ml.CRMSMLPipeline()
    base = {"date_of_birth": "1990-01-01", "gang_id": None, "incident_date": "2024-02-01T14:00:00"}
    low = pipeline.predict({**base, "prior_convictions": 0})["risk_score"]
    high = pipeline.predict({**base, "prior_convictions": 8})["risk_score"]
    assert high > low


def test_only_stale_demo_models_are_retrained_automatically():
    current = ml._dataset_sha256(ml.DATASET_PATH)
    demo = {"pipeline_version": ml.PIPELINE_VERSION,
            "dataset": {"dataset_type": "synthetic_demonstration", "sha256": "0" * 64}}
    assert ml.CRMSMLPipeline._is_stale_demo_model(demo)
    fresh = {**demo, "dataset": {**demo["dataset"], "sha256": current}}
    assert not ml.CRMSMLPipeline._is_stale_demo_model(fresh)
    # A demo model from an older pipeline is retrained with the current models.
    assert ml.CRMSMLPipeline._is_stale_demo_model({**fresh, "pipeline_version": "2.0"})
    real = {"pipeline_version": "2.0", "dataset": {"dataset_type": "authorized_historical", "sha256": "0" * 64}}
    assert not ml.CRMSMLPipeline._is_stale_demo_model(real)
    assert not np.isnan(ml.CRMSMLPipeline().predict({})["risk_score"])


def test_legacy_artifacts_with_unknown_gangs_are_rebuilt():
    import pickle
    from sklearn.preprocessing import LabelEncoder

    ml.CRMSMLPipeline()  # ensure active artifacts exist
    with (ml.MODEL_DIR / "encoders.pkl").open("rb") as handle:
        encoders = pickle.load(handle)
    encoders["gang"] = LabelEncoder().fit(["Shadow Syndicate", "Iron Fist", "None"])  # pre-India gang names
    with (ml.MODEL_DIR / "encoders.pkl").open("wb") as handle:
        pickle.dump(encoders, handle)
    ml.METADATA_PATH.unlink()  # legacy artifacts carried no metadata

    rebuilt = ml.CRMSMLPipeline()
    assert set(rebuilt.label_encoder_gang.classes_) == set(GANG_NAMES) | {"None"}
    assert rebuilt.risk_model is not None and ml.METADATA_PATH.exists()
