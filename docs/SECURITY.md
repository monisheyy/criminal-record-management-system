# Security model and threat model

AI-CRMS stores highly sensitive personal and investigative data. This document summarises the assets, threats and the controls implemented in code. It is not a penetration test or a legal compliance assessment.

## Assets

Criminal records and case files (incl. victims, complainants, evidence references) · user accounts and sessions · the audit trail · AI model artifacts and their outputs · backups.

## Actors and trust boundaries

| Actor | Access |
|---|---|
| Administrator | Everything, incl. users, audit log, model activation |
| Investigating officer | Records directory; cases assigned to them or unassigned; AI outputs for their cases |
| Record clerk | Records and case data entry/exports; **no** AI outputs or admin functions |
| Anonymous | Login and password recovery only |

Boundaries: browser ↔ nginx (TLS) ↔ API ↔ database / model files. Everything from the browser is untrusted.

## Threats and controls (STRIDE)

| Threat | Controls |
|---|---|
| **Spoofing** — credential stuffing, brute force, stolen sessions | Account lockout with identical generic errors and timing equalisation; per-IP rate limits (API + nginx); NIST-style password policy with demo/common-password blocklist; forced change of admin-issued and demo passwords; HttpOnly SameSite=Strict session cookie (not readable by JavaScript); short-lived tokens; revocation on logout (`jti`) and bulk invalidation (`token_version`) on password change/reset, role change and deactivation; production deactivates published demo credentials. |
| **Tampering** — altering records, audit history, model artifacts | Strict input validation; transactional writes; append-only audit and AI-review tables (DB triggers + ORM guard); per-entry HMAC with integrity verification; ML artifacts verified by SHA-256 + HMAC **before unpickling**; CSRF check (`X-Requested-With`) on cookie-authenticated writes; WebSocket Origin allowlist. |
| **Repudiation** | Every security-relevant action is audited with actor, role, target, outcome, reason and request ID; reasons are mandatory for closures, deletions, sensitive record corrections, AI reviews and model activation. |
| **Information disclosure** | Role and object-level authorization (route matrix tests cover every endpoint); clerks' exports exclude AI output; officer directory exposes names/badges only; errors never echo submitted values or stack traces; logs exclude query strings and record content; audit metadata redacts contact details and secrets; `Cache-Control: no-store`; CSP; formula-injection-safe spreadsheets. |
| **Denial of service** | Page-size limits, pagination, rate limits, bounded similarity search, request timeouts at nginx. |
| **Elevation of privilege** | Server-side role checks on every route; admins cannot demote/deactivate themselves; the last active admin cannot be removed; `javascript:`/`data:` URLs rejected; `TrustedHostMiddleware` in production. |

## Responsible-AI controls

Model outputs are advisory only, labelled as unverified decision support everywhere, never modify official record fields, require reasoned human review (with correction history), and synthetic/unvalidated models cannot run in production. See [MODEL_CARD.md](MODEL_CARD.md).

## Known residual risks

* Rate limiting and metrics are per process; enforce limits at the edge for multi-worker/multi-host deployments (nginx config included).
* No multi-factor authentication yet — recommended before production use.
* Evidence files are referenced by URL; there is no managed upload store with malware scanning.
* A database superuser can drop the append-only triggers; HMAC verification detects edits but deletion detection relies on ID-gap review. Consider shipping audit events to a write-once external log store.

## Reporting a vulnerability

Do not open a public issue. Contact the system owner privately with steps to reproduce.
