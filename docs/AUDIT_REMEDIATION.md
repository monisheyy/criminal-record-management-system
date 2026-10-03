# Audit remediation report

Response to *AI-CRMS Project Improvement Audit* (2 October 2026). Every audit
item is listed with its status, what changed, and the evidence (test or file)
that demonstrates it.

**Status key:** ✅ Done · 🟡 Partial (what remains is stated) · ⛔ Not done (outside what code can deliver)

## Summary

| Area | ✅ | 🟡 | ⛔ |
|---|---|---|---|
| P0 Security & repository hygiene | 4 | – | – |
| P0 AI validity, safety & governance | 3 | 3 | – |
| P1 Backend, data integrity & API | 5 | 1 | – |
| P1 Frontend & usability | 5 | 1 | – |
| P1 Testing, CI/CD & release | 5 | – | – |
| P2 Data quality, reporting & future | 3 | 3 | – |

Verification at the time of writing: **213 backend tests**, **19 frontend unit/contract tests**,
**6 Playwright end-to-end tests** (real browser + real API), `vite build`, `oxlint`, `alembic check`, `pip-audit` and
`npm audit` all pass. See [`VERIFICATION_STATUS.md`](../VERIFICATION_STATUS.md).

---

## Defects found during remediation (not listed in the audit)

The audit asked for "real workflow validation". Doing it surfaced these concrete bugs, all fixed:

| Defect | Impact | Fix / evidence |
|---|---|---|
| Case creation sent `priority: "Medium"` (API accepts lowercase `low/normal/high/critical`) | **Creating a case from the UI always failed (422)** | `Cases.jsx` uses API enums; API also normalises legacy casing. `test_case_priority_from_legacy_ui_values_is_normalised`, E2E case workflow |
| Victim form sent `name/contactInfo/condition`; evidence form sent `status: "Collected"`, `location` | **Adding victims or evidence always failed** | `CaseDetails.jsx` rewritten against the real schema; E2E case workflow |
| Linked criminals rendered as "Record #undefined"; officers assigned by typing raw user IDs | Case workspace unusable | Linked-person table, officer picker (`GET /api/users/officers`) |
| Duplicate check sent `firstName` and read a non-existent `matchFound` | **Duplicate warning never worked** | Fixed request/response; create-time 409 guard for strong matches. `test_strong_duplicate_blocks_creation_until_acknowledged` |
| API stored confidences as 0–1, seeder as 0–100, UI printed raw values with "%" | Live predictions showed **"0.6%"** for 60% | Migration 0002 normalises data; shared `formatScore`; seeder fixed. `test_legacy_database_is_adopted_and_data_fixed`, `utils.test.mjs` |
| Profile page rendered nested `input_features` objects as React children | **Page crashed after running a prediction** | New `ExplanationPanel`; route-level error boundaries |
| Lists fetched 50 rows and filtered client-side | Records beyond the newest 50 were invisible/unsearchable | Server-side search/filter/sort/pagination with `X-Total-Count` |
| Record clerks could list all AI predictions (other AI endpoints denied them) | Inconsistent authorization | `require_officer_or_admin`; `test_clerk_cannot_list_or_run_ai_predictions` |
| Officers could add evidence/victims to cases assigned to other officers | Object-level authorization gap | Shared `ensure_case_access`; `test_officer_cannot_touch_case_assigned_to_another_officer` (8 cases) |
| Notification read state was a single column shared by everyone in a role | One admin reading an alert cleared it for all admins | `notification_reads` table; `test_notification_read_state_is_per_user` |
| Test suite retrained and **overwrote the developer's active model files** | Every test run changed tracked files | `AI_CRMS_MODEL_DIR` isolation in `conftest.py` |
| "ACTIVE" model badge was simply the newest row | Governance UI misreported the active model | Uses `is_active` |
| Seeder fabricated human review decisions, audit log entries (fake IPs) and a "87.4% accuracy" alert | Misleading accountability data | Seeded predictions stay pending; one honest `DEMO_DATA_SEEDED` audit event |
| Dashboard showed reviewer agreement as "Model Precision Rating" | Overstated model performance | Relabelled "Reviewer agreement rate — not model accuracy" (UI, PDF, Excel) |
| Excel exports wrote cell values starting with `= + - @` verbatim | Spreadsheet formula injection (CWE-1236) | `_excel_safe`; `test_excel_exports_neutralise_formula_injection` |
| Seeder printed emoji | **API start-up crashed** on non-UTF-8 consoles (Windows services, pipes) | ASCII logging (found by the E2E run) |
| 19 known vulnerabilities in pinned dependencies (python-jose/ecdsa, starlette, python-multipart, python-dotenv, pytest) | Exploitable library flaws | PyJWT replaces python-jose; upgrades; `pip-audit` clean; enforced in CI |
| Deleting a gang/criminal/user that was still referenced raised an unhandled 500 | Crashes, partial operations | Explicit 409s with guidance; global `IntegrityError` → 409 |
| Muted text colour `#98A2B3` on white (2.6:1) | Fails WCAG AA contrast | `#667085` (4.8:1) |

---

## P0 — Immediate: security and repository hygiene

| Item | Status | What was done | Evidence |
|---|---|---|---|
| Secrets in project archive | ✅ | `.env` was never committed (verified with `git log --all -- .env`). Added sanitised [`.env.example`](../.env.example); `.gitignore` covers `.env*`, keys, DBs. **Action for you:** the `.env` that was inside the shared ZIP should be treated as exposed — generate a new `SECRET_KEY` (this invalidates all sessions and requires retraining/re-activating models, see OPERATIONS). | `scripts/package_release.py --check` (also in CI) |
| Clean source package | ✅ | `scripts/package_release.py` builds archives from **git-tracked files only** and fails on forbidden paths (`.env`, `*.db`, `node_modules`, `__pycache__`, `.kilo`, `*.pkl`, `dist`) or secret patterns. Generated model artifacts (26 files) untracked. `.dockerignore` files added. | CI job `release-hygiene` |
| Demo account hardening | ✅ | Seeding only when `SEED_DEMO_DATA=true`, refused in production; demo users flagged `must_change_password`; production start-up **deactivates any account still using a published demo password**; demo buttons only in dev builds. Lockout after N failures (identical generic error, timing-equalised), per-IP rate limits, token revocation (`jti` denylist on logout) and bulk invalidation (`token_version` on password change/reset, role change, deactivation). NIST-style password policy (length + blocklist). | `test_security_hardening.py` (21 tests) |
| Production configuration | ✅ | `app/config.py` validates every setting at start-up; `APP_ENV=production` refuses wildcard/HTTP CORS, demo data, dev OTP provider, insecure cookies, missing `TRUSTED_HOSTS`, synthetic models; disables API docs; enables HSTS. Safe error contracts (no stack traces, no echoed input, request ID). Docker image runs uvicorn without `--reload`, as non-root. | `test_production_configuration_refuses_unsafe_settings` (7 cases) |

## P0 — AI validity, safety and model governance

| Item | Status | What was done | Evidence |
|---|---|---|---|
| Real-data validation | 🟡 | Code cannot create a lawful real-world dataset. What *is* enforced: models of synthetic/unknown provenance cannot be activated, are disabled entirely in production (`AI_ALLOW_SYNTHETIC_MODELS=false`), and every output, report and screen labels them "DEMO / RESEARCH MODE — unverified decision support, not evidence". **Remaining:** acquire, document and legally approve a representative evaluation dataset (see MODEL_CARD). | `test_predictions_disabled_for_synthetic_model_when_not_allowed`, `test_activation_requires_justification_and_blocks_synthetic` |
| Model quality gates | ✅ | Configurable release gate (macro-F1, balanced accuracy, zero-recall classes, minimum test size, calibration error, must beat majority baseline) computed at training and **enforced at activation**. Calibration (ECE, Brier, reliability table) added to metrics. | `test_quality_gate_fails_on_poor_metrics`, `test_activation_blocked_when_quality_gate_failed` |
| Bias and subgroup evaluation | 🟡 | Per-slice accuracy/macro-F1 with sample sizes and worst-case gap (age band, gang membership, location-risk band, time of day), shown in Model Governance. **Remaining:** the dataset has no protected attributes, so protected-group fairness cannot be measured; add legally permissible subgroup columns to the evaluation set. | `test_training_reports_calibration_subgroups_and_quality_gate` |
| Human review & contestability | ✅ | Every decision requires written reasoning (≥10 chars) and a valid override category; decisions are appended to an **append-only** `ai_prediction_reviews` history (DB triggers + ORM guard); later corrections are recorded, never overwritten; outputs never change official record fields; high-score alerts go to the assigned officer, deduplicated. | `test_review_requires_documented_reasoning` (6), `test_review_history_is_append_only_and_records_corrections`, E2E review flow |
| Model lifecycle | 🟡 | Candidate → active → retired lifecycle, justified activation, **rollback** endpoint, dataset SHA-256 versioning, immutable per-candidate evaluation metadata, audit events for training/activation/rollback, deterministic seeds, and **artifact integrity**: SHA-256 + HMAC signature verified *before* unpickling. **Remaining:** production drift monitoring (needs real outcome data) and a separate approver role (four-eyes) if policy requires it. | `test_tampered_artifact_is_refused_before_unpickling`, `test_forged_hashes_without_secret_fail_signature_check` |
| Explainability limits | 🟡 | Explanation panel leads with validity, calibration and missing-input warnings (defaulted features are flagged per row), shows input provenance (record version, model, dataset type), the fixed-weight risk breakdown, and states that importances are global and non-causal. **Remaining:** per-prediction local explanations (e.g. SHAP) — deliberately not added while the model is demo-only. | `test_prediction_carries_advisory_notice_provenance_and_fraction_units` |

## P1 — Backend, data integrity and API

| Item | Status | What was done | Evidence |
|---|---|---|---|
| Database migrations | ✅ | Alembic with baseline (0001) + governance (0002) migrations, tested upgrade/downgrade, drift check, and automatic adoption of pre-Alembic databases (your existing `acrms.db` migrated cleanly in testing). Production never alters schema at start-up; it refuses to start until `alembic upgrade head` has been run. | `test_migrations_upgrade_downgrade_and_match_models`, `test_legacy_database_is_adopted_and_data_fixed`, `test_production_refuses_to_start_on_outdated_schema` |
| Transactional workflows | ✅ | All references validated before writing; business change + audit entry committed in one transaction; explicit rollback; uniqueness conflicts → 409. | `test_failed_case_creation_leaves_no_partial_records` |
| Authorization coverage | ✅ | Auto-generated matrix: **every** protected route rejects anonymous calls; admin-only endpoints reject officers and clerks; object-level case access for all case-scoped reads/writes/exports; clerk exports exclude AI output. | `test_authorization_matrix.py` (~95 parametrised checks incl. route-inventory guard) |
| Input validation | ✅ | Strict Pydantic input schemas: DB-matching lengths, enumerated vocabularies (normalised casing), name/phone/hash patterns, `http(s)`-only URLs (blocks `javascript:`), no future dates, FIR-after-incident, ranges, LIKE-wildcard escaping, sort allowlists, page-size limits. Permissive output schemas so legacy rows never 500. | `test_input_validation.py` (20) |
| Audit trail integrity | ✅ | Actor, role, action, target, outcome, reason, IP, **request/correlation ID** and HMAC `entry_hash` on every entry; append-only via DB triggers (SQLite & PostgreSQL) and ORM guard; admin "Verify integrity" detects modified rows. | `test_audit_log_verification_detects_tampering`, `test_audit_log_rows_are_append_only_in_orm_and_database` |
| API robustness | ✅ | Pagination (`X-Total-Count`), filter/sort limits, auth rate limiting (+ nginx edge limit), request IDs, structured JSON logs without PII, liveness `/api/health` and readiness `/api/health/ready`, consistent error envelope, security headers. | `test_list_endpoints_expose_total_and_enforce_limits`, `test_security_headers_and_request_id`, `test_readiness_reports_schema_at_head` |
| Database scale & recovery | 🟡 | PostgreSQL supported (driver, Docker Compose, PG audit triggers); online SQLite backup/verify/restore tool with checksums, integrity check and safety copy; restore drill is an automated test. **Remaining:** agree RPO/RTO and schedule backups/drills in your environment. | `test_backup_verify_and_restore_round_trip`, `test_corrupted_backup_is_rejected` |

## P1 — Frontend and usability

| Item | Status | What was done |
|---|---|---|
| Real workflow validation | ✅ | Every screen re-checked against the API; the broken workflows in the defects table were fixed and are covered by Playwright E2E. |
| Loading/error/empty states | ✅ | Shared `LoadingState`/`ErrorState` (with retry)/`EmptyState`; `getErrorMessage` renders every API error shape (incl. validation arrays that previously crashed toasts) and request IDs; no silent `catch(() => {})` on data loads. |
| Search & record usability | ✅ | Server-side search/filter/sort/pagination; duplicate warnings with links; case↔person navigation; officer picker; safe downloads using server filenames. |
| Accessibility & responsive design | 🟡 | Skip link, landmarks, labelled controls, visible focus, accessible dialogs (focus trap, Escape, focus return), ARIA tabs, table captions/scopes, chart text alternatives, live regions, WCAG-AA contrast, reduced-motion, phone/tablet layouts. **Remaining:** a manual screen-reader audit and automated axe checks. |
| Authentication storage | ✅ | Token moved from `localStorage` to an **HttpOnly, SameSite=Strict cookie** + `X-Requested-With` CSRF check; WebSocket authenticates via cookie with Origin allowlist (no token in URLs); short-lived tokens; real server-side logout. |
| Frontend quality | ✅ | Placeholder code removed; centralised API/error handling; route-level error boundaries; route code-splitting (initial JS 661 KB → 340 KB); role-specific navigation tested in E2E. |

## P1 — Testing, CI/CD and release readiness

| Item | Status | What was done |
|---|---|---|
| Automated test coverage | ✅ | 60 → 213 backend tests: validation failures, cross-user/object access, expired/invalid/revoked tokens, lockout, rate limits, recovery, rollback/atomicity, migrations, backup/restore, report downloads, audit tamper detection. |
| End-to-end tests | ✅ | Playwright: sign-in/forced password change, cookie hygiene, case workflow (create, victim, evidence, link, close), clerk restrictions, AI assessment + reasoned review, governance, audit verification, logout. |
| Continuous integration | ✅ | `.github/workflows/ci.yml`: backend tests + coverage, migration up/down/drift, `pip-audit`, frontend lint/test/build, `npm audit`, E2E, release-hygiene scan. |
| Dependency management | ✅ | Exact pins split into `requirements.txt` / `requirements-dev.txt`; unused packages removed; lockfile; Dependabot; documented patch process. |
| Deployment & operations | ✅ | Dockerfiles (non-root, healthchecks), nginx same-origin proxy with CSP, Compose stack with PostgreSQL and explicit migration step, `.env.example`, [OPERATIONS.md](OPERATIONS.md) (deploy, backup/restore, key rotation, monitoring, incident response). *Docker files were written but could not be built in this environment (no Docker installed).* |

## P2 — Data quality, reporting and future capability

| Item | Status | What was done / remaining |
|---|---|---|
| Data provenance & quality | 🟡 | Correction history with mandatory reasons for sensitive fields, duplicate detection/acknowledgement, prediction input provenance. **Remaining:** per-field source/validation-status tracking. |
| Evidence management | 🟡 | File SHA-256 field, uploader, append-only chain-of-custody log, permission checks. **Remaining:** the app stores file *references* only — real upload with object storage, retention rules and access logs is future work. |
| Reporting & exports | ✅ | Role-aware exports (clerks get no AI output), UTC-labelled timestamps, "generated by", unverified-AI disclaimers, formula-injection protection, export audit events. |
| Notifications | ✅ | Per-user read receipts, deduplication, targeted delivery, server-side unread counts, polling fallback for dropped WebSockets. |
| Observability | 🟡 | Structured logs, request IDs, admin metrics endpoint (per-route counts/errors/latency), readiness probe, model integrity status. **Remaining:** export to a monitoring stack (Prometheus/OpenTelemetry) and alerting. |
| Documentation | ✅ | README, this report, [SECURITY.md](SECURITY.md) (threat model), [MODEL_CARD.md](MODEL_CARD.md), [OPERATIONS.md](OPERATIONS.md), updated testing strategy and verification status. |

## Release acceptance checklist

| Checklist item | Status |
|---|---|
| No secrets, live database, node_modules, caches, or agent worktrees in release archive | ✅ enforced by `package_release.py` + CI |
| All backend and frontend tests pass in a clean environment; CI runs on pull requests | ✅ verified in a fresh virtualenv; CI workflow added (runs once pushed to GitHub) |
| Role and object-level access tests cover all sensitive endpoints and exports | ✅ |
| Database migrations, backup, restore and rollback procedures are tested | ✅ |
| ML activation blocked unless validation gates pass; synthetic models marked demo-only | ✅ |
| Production uses HTTPS, restricted CORS, secret management, disabled demo credentials, monitoring, incident response | 🟡 enforced/documented in code and config; HTTPS termination, secret store and monitoring stack depend on your hosting |
