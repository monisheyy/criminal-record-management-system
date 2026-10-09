import csv
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def pipeline():
    return CRMSMLPipeline()

from app.ml.pipeline import (
    DATASET_PATH,
    FEATURE_COLUMNS,
    CRMSMLPipeline,
    DatasetValidationError,
    load_training_dataset,
)


def test_versioned_dataset_loads_and_validates():
    X, y_crime, y_gang, metadata = load_training_dataset()
    assert DATASET_PATH.exists()
    assert X.shape == (6000, len(FEATURE_COLUMNS))
    assert len(y_crime) == 6000
    assert len(y_gang) == 6000
    assert metadata["dataset_type"] == "synthetic_demonstration"
    assert metadata["sha256"]


def test_training_is_reproducible_without_saving():
    first = CRMSMLPipeline()
    second = CRMSMLPipeline()
    first_metrics = first.train(save=False)
    second_metrics = second.train(save=False)

    assert first_metrics["model_version"] == second_metrics["model_version"]
    assert first_metrics["crime_classifier"] == second_metrics["crime_classifier"]
    assert first_metrics["gang_predictor"] == second_metrics["gang_predictor"]
    assert first_metrics["feature_importances"] == second_metrics["feature_importances"]

    sample = {
        "id": 999999,
        "prior_convictions": 3,
        "date_of_birth": "1990-01-01T00:00:00",
        "crime_type": "Drug Trafficking",
        "gang_id": 1,
        "is_wanted": True,
        "is_incarcerated": False,
        "known_associates": "1,2,3",
    }
    assert first.predict(sample) == second.predict(sample)


def test_missing_numeric_values_are_imputed():
    X, y_crime, y_gang, _ = load_training_dataset()
    X = X.copy()
    X[0, 0] = np.nan

    pipeline = CRMSMLPipeline()
    result = pipeline.train(X, y_crime, y_gang, save=False)
    assert pipeline.imputer is not None
    assert result["crime_classifier"]["training_samples"] == 4800


def test_dataset_rejects_unknown_target_class(tmp_path: Path):
    source = DATASET_PATH.read_text(encoding="utf-8")
    lines = source.splitlines()
    cells = lines[1].split(",")
    cells[len(FEATURE_COLUMNS) + 1] = "UnknownGang"  # gang_label column
    lines[1] = ",".join(cells)
    invalid = tmp_path / "invalid.csv"
    invalid.write_text("\n".join(lines) + "\n", encoding="utf-8")

    try:
        load_training_dataset(invalid)
    except DatasetValidationError as exc:
        assert "Unknown gang classes" in str(exc)
    else:
        raise AssertionError("Invalid target class was accepted")


def test_risk_score_is_deterministic_and_explainable():
    pipeline = CRMSMLPipeline()
    data = {
        "prior_convictions": 3, "violence_history": 2,
        "gang_id": 1, "is_wanted": True, "is_incarcerated": False,
        "crime_type": "Robbery",
    }
    first = pipeline._calculate_risk_score(data, 0.8, 0.7)
    second = pipeline._calculate_risk_score(data, 0.8, 0.7)
    assert first == second
    score, factors = first
    assert 1 <= score <= 100
    assert factors
    assert all("contribution" in factor and "weight" in factor for factor in factors)


def test_risk_levels_use_configured_thresholds():
    pipeline = CRMSMLPipeline()
    assert pipeline._risk_level(1) == "low"
    assert pipeline._risk_level(34.9) == "low"
    assert pipeline._risk_level(35) == "medium"
    assert pipeline._risk_level(55) == "high"
    assert pipeline._risk_level(75) == "critical"


def test_risk_score_missing_values_are_handled():
    pipeline = CRMSMLPipeline()
    score, factors = pipeline._calculate_risk_score({"crime_type": "Fraud"}, 0.5, 0.2)
    assert 1 <= score <= 100
    assert factors


def test_risk_score_rejects_invalid_values():
    pipeline = CRMSMLPipeline()
    for bad in ({"prior_convictions": -1}, {"prior_convictions": "abc"}, {"is_wanted": "yes"}, {"crime_type": "NotARealCrime"}):
        try:
            pipeline._calculate_risk_score(bad, 0.5, 0.2)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Invalid risk input accepted: {bad}")


def test_persisted_evaluation_metadata_matches_training_output():
    import json
    from app.ml.pipeline import METADATA_PATH

    pipeline = CRMSMLPipeline()
    result = pipeline.train(save=True)
    stored = json.loads(METADATA_PATH.read_text(encoding="utf-8"))

    assert stored["model_version"] == result["model_version"]
    assert stored["evaluation_method"] == result["evaluation_method"]
    assert stored["crime_classifier"]["accuracy"] == result["crime_classifier"]["accuracy"]
    assert stored["crime_classifier"]["precision"] == result["crime_classifier"]["precision"]
    assert stored["crime_classifier"]["recall"] == result["crime_classifier"]["recall"]
    assert stored["crime_classifier"]["f1"] == result["crime_classifier"]["f1"]
    assert stored["crime_classifier"]["confusion_matrix"] == result["crime_classifier"]["confusion_matrix"]
    assert stored["gang_predictor"]["accuracy"] == result["gang_predictor"]["accuracy"]


def test_evaluation_contains_per_class_and_distribution():
    pipeline = CRMSMLPipeline()
    result = pipeline.train(save=False)
    for key in ("crime_classifier", "gang_predictor"):
        evaluation = result[key]
        assert evaluation["test_samples"] == 1200
        assert len(evaluation["per_class"]) == len(evaluation["classes"])
        assert sum(evaluation["class_distribution"].values()) == evaluation["test_samples"]
        assert len(evaluation["confusion_matrix"]) == len(evaluation["classes"])


def test_prediction_explanation_matches_permutation_importances(tmp_path):
    from app.ml.pipeline import CRMSMLPipeline, FEATURE_COLUMNS

    pipeline = CRMSMLPipeline()
    pipeline.train(save=True)
    data = {
        "id": 999,
        "prior_convictions": 2,
        "crime_type": "Robbery",
        "gang_id": 1,
        "is_wanted": True,
        "is_incarcerated": False,
        "date_of_birth": "1995-01-01",
        "known_associates": "1,2,3",
        "violence_history": 2,
    }
    result = pipeline.predict(data)
    explanation = result["input_features"]["explanation"]
    stored = pipeline.training_metadata["feature_importances"]
    total = sum(stored.values())
    assert total > 0
    assert explanation["method"] == "global_permutation_importance"
    assert explanation["model_version"] == pipeline.model_version
    assert len(explanation["all_features"]) == len(FEATURE_COLUMNS)
    for row in explanation["all_features"]:
        assert row["relative_importance"] == round(stored[row["feature"]] / total, 6)
    assert explanation["top_features"] == sorted(
        explanation["all_features"],
        key=lambda item: (-item["relative_importance"], item["feature"]),
    )[:5]


def test_prediction_explanation_is_deterministic(tmp_path):
    from app.ml.pipeline import CRMSMLPipeline

    pipeline = CRMSMLPipeline()
    pipeline.train(save=True)
    data = {"prior_convictions": 1, "crime_type": "Assault", "gang_id": None, "is_wanted": False}
    first = pipeline.predict(data)["input_features"]["explanation"]
    second = pipeline.predict(data)["input_features"]["explanation"]
    assert first == second


def test_similarity_same_vector_has_maximum_similarity(pipeline):
    target = {
        "id": 100,
        "prior_convictions": 2,
        "crime_type": "Robbery",
        "gang_id": 1,
        "is_wanted": True,
        "is_incarcerated": False,
        "date_of_birth": "1990-01-01",
        "known_associates": "A,B",
    }
    results = pipeline.find_similar_criminals(target, [target, {**target, "id": 101}], top_k=5)
    assert len(results) == 1
    assert results[0]["id"] == 101
    assert results[0]["similar_record_id"] == 101
    assert results[0]["score"] == 100.0
    assert results[0]["similarity_score"] == 100.0
    assert isinstance(results[0]["matching_features"], list)


def test_similarity_excludes_current_record_and_orders_descending(pipeline):
    target = {"id": 1, "prior_convictions": 2, "crime_type": "Robbery", "gang_id": 1}
    records = [
        target,
        {"id": 2, "prior_convictions": 2, "crime_type": "Robbery", "gang_id": 1},
        {"id": 3, "prior_convictions": 0, "crime_type": "Vandalism", "gang_id": None},
        {"id": 4, "prior_convictions": 1, "crime_type": "Assault", "gang_id": 1},
    ]
    results = pipeline.find_similar_criminals(target, records, top_k=3)
    assert all(item["id"] != 1 for item in results)
    assert [item["score"] for item in results] == sorted([item["score"] for item in results], reverse=True)
    assert [item["similarity_score"] for item in results] == sorted([item["similarity_score"] for item in results], reverse=True)
    assert results[0]["id"] == 2
    assert results[0]["similar_record_id"] == 2


def test_similarity_handles_missing_values_without_crashing(pipeline):
    target = {"id": 10, "prior_convictions": None, "crime_type": None, "gang_id": None, "known_associates": None}
    records = [
        target,
        {"id": 11, "prior_convictions": None, "crime_type": None, "gang_id": None, "known_associates": None},
        {"id": 12, "prior_convictions": 1, "crime_type": "Fraud", "gang_id": None},
    ]
    results = pipeline.find_similar_criminals(target, records, top_k=5)
    assert results
    assert all(0.0 <= item["score"] <= 100.0 for item in results)
    assert all("matching_features" in item for item in results)


def test_inference_features_do_not_depend_on_target_label():
    pipeline = CRMSMLPipeline()
    common = {
        "prior_convictions": 2,
        "date_of_birth": "1990-01-01T00:00:00",
        "gang_id": 1,
        "is_wanted": False,
        "known_associates": "a,b",
    }
    robbery = pipeline._extract_features({**common, "crime_type": "Robbery"})
    fraud = pipeline._extract_features({**common, "crime_type": "Fraud"})
    assert robbery == fraud


def test_explicit_observed_features_are_used():
    pipeline = CRMSMLPipeline()
    features = pipeline._extract_features({
        "prior_convictions": 2,
        "is_gang_member": 1,
        "weapons_involved": 1,
        "drug_involvement": 1,
        "financial_motivation": 0,
        "tech_involvement": 1,
        "violence_history": 3,
        "location_risk": 0.8,
        "time_of_crime": 22,
        "associates_count": 7,
    })
    assert features[2:7] == [1.0, 1.0, 1.0, 0.0, 1.0]
    assert features[7:11] == [3.0, 0.8, 22.0, 7.0]


def test_case_details_are_one_hot_inputs_and_unrecorded_details_are_missing():
    from app.ml.pipeline import CASE_DETAIL_COLUMNS

    columns = {name: i for i, name in enumerate(FEATURE_COLUMNS)}
    features = CRMSMLPipeline._extract_features(
        {"location_type": "Online", "target_type": "data"}, impute_missing=True)
    assert [features[columns[name]] for name in CASE_DETAIL_COLUMNS["location_type"]] == [0, 0, 0, 0, 0, 1]
    assert features[columns["target_data"]] == 1.0 and features[columns["target_money"]] == 0.0
    assert all(np.isnan(features[columns[name]]) for name in CASE_DETAIL_COLUMNS["modus_operandi"])
    quality = CRMSMLPipeline._feature_input_quality({"location_type": "online"})
    assert set(CASE_DETAIL_COLUMNS["location_type"]) <= set(quality["observed_features"])
    assert "method_deception" in quality["defaulted_features"]
    with pytest.raises(ValueError, match="modus_operandi must be one of"):
        CRMSMLPipeline._extract_features({"modus_operandi": "telepathy"})


def test_dataset_without_case_detail_columns_still_loads(tmp_path: Path):
    from app.ml.pipeline import BASE_FEATURE_COLUMNS, TARGET_COLUMNS

    with DATASET_PATH.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))[:200]
    older = tmp_path / "older.csv"
    with older.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=BASE_FEATURE_COLUMNS + TARGET_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    X, _, _, meta = load_training_dataset(older)
    assert X.shape == (200, len(FEATURE_COLUMNS))
    assert np.isnan(X[:, FEATURE_COLUMNS.index("method_deception")]).all()
    assert meta["missing_counts"]["method_deception"] == 200


def test_candidate_save_does_not_overwrite_active_artifacts(tmp_path, monkeypatch):
    import hashlib
    import app.ml.pipeline as ml_module

    active_files = [
        ml_module.MODEL_DIR / "crime_classifier.pkl",
        ml_module.MODEL_DIR / "gang_predictor.pkl",
        ml_module.MODEL_DIR / "encoders.pkl",
        ml_module.MODEL_DIR / "metadata.json",
    ]
    before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in active_files}
    candidates_dir = tmp_path / "candidates"
    monkeypatch.setattr(ml_module, "CANDIDATES_DIR", candidates_dir)

    candidate = CRMSMLPipeline()
    candidate.train(save=False)
    candidate_path = Path(candidate.save_candidate())

    assert candidate_path.is_dir()
    assert all((candidate_path / name).is_file() for name in (
        "crime_classifier.pkl", "gang_predictor.pkl", "encoders.pkl", "metadata.json"
    ))
    after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in active_files}
    assert before == after


def test_metrics_include_class_imbalance_and_majority_baseline():
    from app.ml.pipeline import CRMSMLPipeline

    # Three classes with a majority-class baseline of 0.5; class C is never predicted.
    metrics = CRMSMLPipeline._metrics(
        np.asarray([0, 0, 1, 1, 1, 2]),
        np.asarray([0, 0, 1, 1, 1, 1]),
        training_samples=24,
        test_samples=6,
        classes=["A", "B", "C"],
    )
    assert metrics["majority_baseline_accuracy"] == 0.5
    assert metrics["balanced_accuracy"] < metrics["accuracy"]
    assert metrics["macro_f1"] >= 0
    assert metrics["zero_recall_classes"] == ["C"]
    assert metrics["predicted_class_distribution"]["C"] == 0
    assert metrics["per_class"]["C"]["support"] == 1


def test_feature_quality_reports_missing_and_derived_inputs():
    from app.ml.pipeline import CRMSMLPipeline, FEATURE_COLUMNS

    quality = CRMSMLPipeline._feature_input_quality({
        "prior_convictions": 2,
        "gang_id": 7,
        "date_of_birth": "1990-01-01T00:00:00",
        "known_associates": "A,B",
        "incident_date": "2025-05-01T21:30:00",
    })
    assert quality["feature_count"] == len(FEATURE_COLUMNS)
    assert "prior_convictions" in quality["observed_features"]
    assert "age" in quality["derived_features"]
    assert "is_gang_member" in quality["derived_features"]
    assert "time_of_crime" in quality["derived_features"]
    assert "weapons_involved" in quality["defaulted_features"]
    assert quality["coverage_percent"] < 100
    assert quality["warning"]


def test_incident_hour_uses_observed_timestamp_not_crime_type():
    from app.ml.pipeline import CRMSMLPipeline

    assert CRMSMLPipeline._incident_hour({"incident_date": "2025-05-01T21:30:00"}) == 21
    assert CRMSMLPipeline._incident_hour({"crime_type": "Murder"}) == 12


def test_gang_classifier_excludes_direct_target_proxy():
    from app.ml.pipeline import CRMSMLPipeline, GANG_FEATURE_COLUMNS, FEATURE_COLUMNS

    pipeline = CRMSMLPipeline()
    metrics = pipeline.train(save=False)
    assert "is_gang_member" not in GANG_FEATURE_COLUMNS
    assert len(GANG_FEATURE_COLUMNS) == len(FEATURE_COLUMNS) - 1
    assert pipeline.gang_predictor.n_features_in_ == len(GANG_FEATURE_COLUMNS)
    assert metrics["gang_predictor"]["test_samples"] > 0
    assert pipeline.training_metadata["model_feature_columns"]["gang_predictor"] == GANG_FEATURE_COLUMNS


def test_legacy_gang_model_is_not_used_for_prediction():
    from app.ml.pipeline import CRMSMLPipeline, FEATURE_COLUMNS

    pipeline = CRMSMLPipeline()
    pipeline.train(save=False)
    # Simulate a legacy artifact whose model was trained with the leaking feature.
    class LegacyGangModel:
        n_features_in_ = len(FEATURE_COLUMNS)
    pipeline.gang_predictor = LegacyGangModel()
    # The legacy model is rejected before calling predict_proba.
    result = pipeline.predict({"prior_convictions": 1, "date_of_birth": "1990-01-01"})
    assert result["gang_prediction_available"] is False
    assert result["predicted_gang"] is None
    assert result["gang_prediction_warning"]
    assert result["gang_affiliation_probability"] == 0.0


def test_candidate_activation_rejects_legacy_or_incompatible_feature_schema(tmp_path):
    import json
    from app.ml.pipeline import CRMSMLPipeline, CANDIDATES_DIR, FEATURE_COLUMNS, PIPELINE_VERSION, GANG_FEATURE_COLUMNS

    pipeline = CRMSMLPipeline()
    candidate_dir = CANDIDATES_DIR / "test-incompatible-schema"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    for name in ("crime_classifier.pkl", "gang_predictor.pkl", "encoders.pkl"):
        (candidate_dir / name).write_bytes(b"placeholder")
    metadata = {
        "pipeline_version": PIPELINE_VERSION,
        "model_feature_columns": {
            "crime_classifier": FEATURE_COLUMNS,
            "gang_predictor": FEATURE_COLUMNS,  # legacy schema leaks is_gang_member
        },
    }
    (candidate_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    try:
        pipeline.activate_candidate(candidate_dir)
    except ValueError as exc:
        assert "target-leaking feature" in str(exc)
    else:
        raise AssertionError("Legacy gang feature schema was accepted")
    finally:
        import shutil
        shutil.rmtree(candidate_dir, ignore_errors=True)


def test_crime_prediction_returns_ranked_top_suggestions():
    from app.ml.pipeline import CRMSMLPipeline, TOP_K_SUGGESTIONS

    pipeline = CRMSMLPipeline()
    metrics = pipeline.train(save=False)
    assert metrics["crime_classifier"][f"top_{TOP_K_SUGGESTIONS}_accuracy"] >= metrics["crime_classifier"]["accuracy"]
    result = pipeline.predict({"prior_convictions": 1, "violence_history": 0, "time_of_crime": 23})
    candidates = result["crime_type_candidates"]
    assert len(candidates) == TOP_K_SUGGESTIONS
    assert candidates[0]["crime_type"] == result["predicted_crime_type"]
    assert [c["score"] for c in candidates] == sorted((c["score"] for c in candidates), reverse=True)
    assert result["input_features"]["crime_type_candidates"] == candidates


def test_derived_features_treat_late_evening_and_early_morning_as_night():
    from app.ml.pipeline import add_derived_features

    hours = np.array([[0.0, 3], [4, 0], [5, 1], [12, 2], [19, 0], [20, 5], [23, 0]])
    derived = add_derived_features(hours, hour_index=0, associates_index=1)
    assert derived[:, 2].tolist() == [1, 1, 0, 0, 0, 1, 1]
    assert np.allclose(derived[:, 3], np.log1p(hours[:, 1]))
