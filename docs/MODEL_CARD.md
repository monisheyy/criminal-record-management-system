# Model card — AI-CRMS crime-category and gang-affiliation classifiers

> **Status: DEMONSTRATION ONLY.** The bundled models are trained on 600 rows of *synthetic* data. They have no established real-world validity and must not inform real investigative, charging, custody or risk decisions. Production configuration blocks them (`AI_ALLOW_SYNTHETIC_MODELS=false`).

## Overview

| | |
|---|---|
| Models | Random Forest crime-category classifier (15 classes); Random Forest gang-affiliation classifier (5 gangs + none) |
| Pipeline version | 2.0 (`backend/app/ml/pipeline.py`) |
| Training data | `backend/app/ml/data/demo_crime_training_v1.csv`, synthetic, SHA-256 pinned in `dataset_manifest.json` |
| Outputs | Suggested crime category + uncalibrated score; gang-association score; a deterministic, fixed-weight *prototype* risk score (1–100) |
| Owner | System administrator(s) operating the Model Governance screen |

## Intended use

Teaching, demonstration and engineering of a human-in-the-loop decision-support workflow. Every output is a prompt for a qualified reviewer to check the underlying record — never evidence, and never a finding of guilt or dangerousness.

## Out-of-scope uses

Any automated or semi-automated decision affecting a person (arrest, charging, bail, sentencing, surveillance targeting, watch-listing); ranking people by "risk"; use on populations or jurisdictions the data does not represent.

## Evaluation

Computed at every training run and stored with the candidate (visible in Model Governance):

* Holdout: when the dataset has an `incident_date` column, the newest 20% of cases (train on the past, test on the future) with forward-chaining time-series cross-validation; otherwise a stratified 80/20 split + 5-fold stratified cross-validation, fixed seed.
* Model/calibration selection (`python -m app.ml.compare_models`) uses only the development portion, never the holdout.
* Accuracy, balanced accuracy, macro and weighted precision/recall/F1, per-class metrics, confusion matrix, majority-class baseline, zero-recall classes.
* **Calibration:** expected calibration error (10 bins), Brier score, reliability table. Optional sigmoid/isotonic calibration (`AI_CRMS_CALIBRATION`) is fitted on training data only; the gate measures the calibrated model. Displayed "confidence" values are still not validated real-world probabilities.
* **Slices:** age band, gang membership, location-risk band, time of day, plus any `slice_*` group columns in the dataset (e.g. district) — with sample sizes; slices under 10 samples are not scored.

## Release gate

A candidate can be activated only if it is not trained on synthetic data **and** it passes the configurable gate (defaults: macro-F1 ≥ 0.60, balanced accuracy ≥ 0.60, no zero-recall classes, ECE ≤ 0.15, ≥ 100 holdout samples, beats the majority baseline), **and** an administrator records a written justification. Passing the gate is necessary, not sufficient.

## Limitations and ethical considerations

* Synthetic data encodes the designer's assumptions; metrics on it say nothing about real performance.
* No protected attributes exist in the data, so fairness across protected groups is **unmeasured**. Historical police data typically reflects enforcement patterns, not underlying offending — a real dataset would risk reproducing those biases.
* Global feature importance is not a causal or individual explanation.
* Missing inputs fall back to defaults; outputs list which features were defaulted, and such outputs are especially unreliable.
* The prototype risk score uses hand-chosen weights and has not been validated against any outcome.

## Requirements before any real-world use

1. Lawful basis, data-protection impact assessment and governance approval.
2. A documented, representative, quality-controlled evaluation dataset with provenance, including legally permissible subgroup attributes.
3. Fairness evaluation across those subgroups and geographies/time periods, with documented mitigations.
4. Independent review of the model and of this card; agreed gate thresholds.
5. Ongoing monitoring of reviewer agreement, overrides and outcome drift, with a rollback plan (Model Governance supports rollback).
