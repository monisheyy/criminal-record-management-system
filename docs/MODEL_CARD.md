# Model card — AI-CRMS crime-category and gang-affiliation classifiers

> **Status: DEMONSTRATION ONLY.** The bundled models are trained on 6,000 rows of *synthetic* India-themed data (fictional gangs, NCRB-informed crime mix, simulated re-arrest outcome; see `backend/app/ml/data/DATASET_SCHEMA.md`). They have no established real-world validity and must not inform real investigative, charging, custody or risk decisions. Production configuration blocks them (`AI_ALLOW_SYNTHETIC_MODELS=false`).

## Overview

| | |
|---|---|
| Models | Logistic-regression crime-category classifier (15 classes); logistic-regression gang-affiliation classifier (6 fictional gangs + none); logistic-regression danger score (P(re-arrest within 2 years)). The crime and gang models add two derived inputs: a night-time flag (20:00–04:59) and log(1 + associates) |
| Pipeline version | 3.0 (`backend/app/ml/pipeline.py`) |
| Training data | `backend/app/ml/data/india_crime_training_v1.csv`, synthetic, SHA-256 pinned in `dataset_manifest.json` |
| Outputs | Suggested crime category + score, plus the top 3 categories ranked; suggested gang + association score; danger score 1–100 = 1 + 99 × P(re-arrest within 2 years), with an exact per-factor breakdown (falls back to the fixed-weight prototype score when the dataset has no `reoffended_2y` outcome) |
| Owner | System administrator(s) operating the Model Governance screen |

## Intended use

Teaching, demonstration and engineering of a human-in-the-loop decision-support workflow. Every output is a prompt for a qualified reviewer to check the underlying record — never evidence, and never a finding of guilt or dangerousness.

## Out-of-scope uses

Any automated or semi-automated decision affecting a person (arrest, charging, bail, sentencing, surveillance targeting, watch-listing); ranking people by "risk"; use on populations or jurisdictions the data does not represent.

## Evaluation

Computed at every training run and stored with the candidate (visible in Model Governance):

* Holdout: when the dataset has an `incident_date` column, the newest 20% of cases (train on the past, test on the future) with forward-chaining time-series cross-validation; otherwise a stratified 80/20 split + 5-fold stratified cross-validation, fixed seed.
* Model/calibration selection (`python -m app.ml.compare_models`) uses only the development portion, never the holdout.
* Accuracy, top-3 accuracy (crime: is the right category among the three suggestions shown), balanced accuracy, macro and weighted precision/recall/F1, per-class metrics, confusion matrix, majority-class baseline, zero-recall classes.
* **Calibration:** expected calibration error (10 bins), Brier score, reliability table. Optional sigmoid/isotonic calibration (`AI_CRMS_CALIBRATION`) is fitted on training data only; the gate measures the calibrated model. Displayed "confidence" values are still not validated real-world probabilities.
* **Slices:** age band, gang membership, location-risk band, time of day, plus any `slice_*` group columns in the dataset (e.g. district) — with sample sizes; slices under 10 samples are not scored.

### Results on the bundled synthetic data (time-based holdout: newest 1,200 incidents)

| Model | Pipeline 3.0 | Pipeline 2.0 (Random Forest) | Best possible on this data | Baseline |
|---|---|---|---|---|
| Crime type, accuracy | **54.3%** | 50.2% | 55.1% | 11% (always guess the most common) |
| Crime type, top-3 accuracy | **85.8%** | not measured | 86.3% | 24% |
| Crime type, macro-F1 / ECE | 0.50 / 0.02 | 0.46 / 0.07 | | |
| Gang, accuracy | **81.5%** | 71.2% | 82.1% | 71.8% (always "None") |
| Gang, balanced accuracy | 52% (per-gang recall 17–69%) | 64% | | 14% (chance across 7 classes) |
| Danger score | AUC 0.774, ECE 0.01; observed re-arrest 23% / 45% / 68% / 86% in low / medium / high / critical | AUC 0.774 (same model) | AUC 0.78 | 43% base rate |

"Best possible" is the Bayes-optimal score: the generator draws every row at random from overlapping crime and gang profiles, so many rows look identical but carry different labels, and no model can beat that limit on average (`python -m app.ml.data.accuracy_ceiling` computes it from the generator's exact probabilities). Pipeline 3.0 is within 1 point of it on every target, so more tuning cannot raise single-guess crime accuracy toward 80% on this data; only richer real inputs can.

Trade-off: the 2.0 gang forest weighted gangs equally, which raised balanced accuracy but made it *less* accurate than always answering "None". The 3.0 model is the most accurate, but it answers "None" for borderline cases, so it finds fewer gang members (Lal Toofan 17% and Kaali Billi 24% recall, because both share night-time burglary and vehicle theft with non-gang offenders).

The model was chosen on development folds only (`compare_models`: logistic regression 52.1% ± 2.0 accuracy and 85.4% top-3 vs Random Forest 48.3% and 81.9%, gradient boosting 45.9% and 79.7%); the holdout above was scored once. The night window matches how the synthetic generator defines night; re-check it on real data.

These numbers show that the models learn the patterns *designed into* the synthetic data. They are not evidence of real-world accuracy.

## Release gate

A candidate can be activated only if it is not trained on synthetic data **and** it passes the configurable gate (defaults: macro-F1 ≥ 0.60, balanced accuracy ≥ 0.60, no zero-recall classes, ECE ≤ 0.15, ≥ 100 holdout samples, beats the majority baseline), **and** an administrator records a written justification. Passing the gate is necessary, not sufficient.

## Limitations and ethical considerations

* Synthetic data encodes the designer's assumptions; metrics on it say nothing about real performance.
* No protected attributes exist in the data, so fairness across protected groups is **unmeasured**. Historical police data typically reflects enforcement patterns, not underlying offending — a real dataset would risk reproducing those biases.
* Global feature importance (permutation importance on the holdout) is not a causal or individual explanation.
* Missing inputs fall back to defaults; outputs list which features were defaulted, and such outputs are especially unreliable.
* The danger score is learned from a *simulated* outcome. Real use would need a real, lawfully obtained outcome (e.g. re-arrest records) and a fairness review; the score must never decide bail, custody or charging.
* Without a `reoffended_2y` column, the fallback prototype score uses hand-chosen weights that have not been validated against any outcome.

## Requirements before any real-world use

1. Lawful basis, data-protection impact assessment and governance approval.
2. A documented, representative, quality-controlled evaluation dataset with provenance, including legally permissible subgroup attributes.
3. Fairness evaluation across those subgroups and geographies/time periods, with documented mitigations.
4. Independent review of the model and of this card; agreed gate thresholds.
5. Ongoing monitoring of reviewer agreement, overrides and outcome drift, with a rollback plan (Model Governance supports rollback).
