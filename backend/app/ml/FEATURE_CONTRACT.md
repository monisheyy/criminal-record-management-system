# AI-CRMS ML Feature Contract and Data Readiness

**Status:** design and audit contract; not approval for operational criminal-risk use.

## Prediction tasks must remain distinct

1. **Case crime-type classification** would classify a case from evidence and incident facts available at a defined point in the investigation. The target must be a verified, adjudicated/validated case label appropriate to the intended use. Do not use the current `crime_type` field as an input when it is also the target.
2. **Gang-label classification** is a separate task. It requires independently verified labels, clear label provenance, careful treatment of unconfirmed allegations, and evaluation that accounts for groups/cases connected to the same people.
3. **Future offending or risk prediction** is a separate high-impact task requiring a defined outcome, prediction horizon, lawful and representative data, calibration, subgroup evaluation, and domain/legal review. Current prototype risk scores are not validated for this purpose.

Do not combine these tasks or treat one model's output as ground truth for another.

## Existing feature availability mapping

| Model feature | Existing source that can be used | Availability / action | Restrictions and validation |
|---|---|---|---|
| `prior_convictions` | `Criminal.prior_convictions` | Present but may be null or stale; preserve null as missing | Count only verified convictions, not arrests, allegations, or open cases. Record as-of date and provenance in any future schema. |
| `age` | `Criminal.date_of_birth` | Derivable when DOB is present | Sensitive/fairness review required; test performance with and without it and do not use as a proxy for guilt. |
| `is_gang_member` | `Criminal.gang_id` | Derivable as a database relationship, but the relationship may not mean verified membership | This feature is excluded from the gang classifier because it directly leaks the `gang_label` target (including whether the label is `None`). Do not treat an allegation or model prediction as verified affiliation. Prefer a provenance/status field before any reviewed use in another task. |
| `weapons_involved` | `Case.weapons_involved` (nullable, officer-recorded) | Observed when recorded; NULL is reported as defaulted | Record from evidence, never infer from crime type. Training rows must use the value as known at the prediction time point. |
| `drug_involvement` | `Case.drug_involvement` (nullable, officer-recorded) | Observed when recorded; NULL is reported as defaulted | Requires verified evidence coding. Never infer from crime type or narrative text without validated extraction and review. |
| `financial_motivation` | `Case.financial_motivation` (nullable, officer-recorded) | Observed when recorded; NULL is reported as defaulted | This is an interpretation, not a raw fact. Use only with an explicit, reviewable case coding standard. |
| `tech_involvement` | `Case.tech_involvement` (nullable, officer-recorded) | Observed when recorded; NULL is reported as defaulted | A `digital` evidence item alone does not establish it; record only a reviewed case-specific annotation. |
| `violence_history` | `CriminalHistory` has free-text events/descriptions; no structured verified count | **Unavailable by default** | Do not count free text or allegations as violence history. Requires a verified, structured history definition. |
| `location_risk` | `Case.location` is free text; no validated geographic baseline exists | **Unavailable by default** | Do not infer neighborhood risk from address or demographics. Exclude unless a documented, lawful, validated source and rationale exist. |
| `time_of_crime` | `Case.incident_date` | Derivable when the timestamp is present | Confirm timezone and whether the field is actual incident time rather than FIR filing time. Missing values must remain flagged. |
| `location_*` (6 one-hot columns) | `Case.location_type` (nullable, officer-recorded vocabulary key) | Observed when recorded; an unrecorded detail is missing in all six columns | Record the place of occurrence as on the FIR, from evidence; never infer it from the crime type. |
| `target_*` (6 one-hot columns) | `Case.target_type` (nullable, officer-recorded) | Observed when recorded; missing otherwise | What the offence was directed at (person, property, vehicle, money, data, contraband). Record the facts, not the suspected charge. |
| `method_*` (9 one-hot columns) | `Case.modus_operandi` (nullable, officer-recorded) | Observed when recorded; missing otherwise | Modus operandi as recorded at the prediction time point. It is close to the offence, so it must be recorded from what happened, never back-filled from the final charge, or evaluation will overstate accuracy. |
| `associates_count` | `Criminal.known_associates` is free text | Weakly derivable only as a rough count | Comma-separated text may contain duplicates, aliases, or unverified links. Do not interpret as culpability. Prefer a verified relationship table and explicit provenance. |

## Gang-model target leakage fix

The previous gang classifier included `is_gang_member`, which was derived from `Criminal.gang_id`. That input directly reveals the target's membership/non-membership status and makes its evaluation misleading. The revised training pipeline uses a separate gang feature list that excludes this column. Legacy loaded gang artifacts with the old eleven-feature signature are disabled at inference rather than trusted. The gang-label identities in the bundled synthetic generator are also assigned randomly among named gangs, so meaningful named-gang prediction cannot be demonstrated from this dataset; that is a dataset limitation, not a reason to infer labels from the target.

## Runtime quality signalling

The inference response stores `input_features.feature_input_quality`, containing observed, derived, and defaulted feature names plus a coverage percentage. This is a completeness indicator only; it is **not** model confidence, calibration, evidence quality, or a risk score. Defaulted fields remain a major source of uncertainty. The application must display the warning and must not imply that the prediction is reliable merely because a model returned a score.

## Dataset and evaluation gates

- The bundled CSV is synthetic demonstration data. It is suitable for tests and pipeline demonstrations only.
- Any external dataset must have an owner, lawful-use approval, label definition, source/version, collection time, inclusion/exclusion criteria, missingness analysis, and SHA-256 fingerprint.
- Split by case/person/group when related rows could otherwise leak across train and test; for time-dependent tasks use a time-based holdout. Keep the final holdout untouched until model selection is complete.
- Report accuracy, balanced accuracy, macro and weighted precision/recall/F1, per-class support and predicted counts, confusion matrix, majority-class baseline, and zero-recall classes. Report uncertainty intervals where sample size permits.
- For probability outputs, assess calibration (e.g. reliability curve/Brier score) on a representative held-out set. Do not call raw `predict_proba` values validated real-world probabilities.
- Predefine release criteria, include subgroup/error analysis where lawful and statistically supportable, record reviewer approval, and preserve a rollback path.
- Do not use model-generated labels as ground truth, automatically retrain from predictions, or automatically change official records/status based on a model score.
