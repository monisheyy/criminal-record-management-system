from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import settings
from app.observability import RequestContextMiddleware, configure_logging, current_request_id

configure_logging(settings.log_level, settings.log_json)
logger = logging.getLogger("ai_crms")

from app.database import SessionLocal, engine  # noqa: E402  (logging must be configured first)
from app.db_bootstrap import current_revision, head_revision, migrate_database  # noqa: E402
from app import models  # noqa: E402
from app.routers import (  # noqa: E402
    admin, ai_predictions, auth, cases, criminals, gangs, intelligence, notifications,
)

APP_VERSION = "1.1.0"

# Published demo credentials (see seed_data.py). They must never work in production.
KNOWN_DEMO_CREDENTIALS = {
    "admin": "admin123", "officer1": "officer123", "officer2": "officer123",
    "officer3": "officer123", "clerk1": "clerk123", "clerk2": "clerk123",
}


def disable_known_demo_credentials(db) -> int:
    """Deactivate any account still using a published demo password."""
    from app.security import invalidate_all_sessions, verify_password
    from app.utils.audit import create_audit_log

    disabled = 0
    for username, password in KNOWN_DEMO_CREDENTIALS.items():
        user = db.query(models.User).filter(models.User.username == username, models.User.is_active.is_(True)).first()
        if user and verify_password(password, user.hashed_password):
            user.is_active = False
            invalidate_all_sessions(user)
            create_audit_log(db, "DEMO_ACCOUNT_DISABLED", user_id=user.id, username=user.username, role=user.role,
                             resource_type="user", resource_id=user.id, status="success",
                             reason="Published demo credential detected at production start-up", commit=False)
            disabled += 1
    if disabled:
        db.commit()
        logger.warning("Disabled %d account(s) still using published demo passwords", disabled)
    return disabled


# Arbitrary constant naming the PostgreSQL advisory lock taken at start-up.
STARTUP_LOCK_ID = 7_310_442


@asynccontextmanager
async def startup_lock():
    """Serialise start-up work across worker processes.

    The Docker image runs several uvicorn workers; without this they would all
    migrate and seed an empty database at once and the losers would crash on
    unique constraints. SQLite deployments run a single process.
    """
    if engine.dialect.name != "postgresql":
        yield
        return
    with engine.connect() as connection:
        connection.execute(text("SELECT pg_advisory_lock(:id)"), {"id": STARTUP_LOCK_ID})
        try:
            yield
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": STARTUP_LOCK_ID})


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with startup_lock():
        # Schema: auto-migrate in development/test; verify-only in production.
        migrate_database(engine, allow_auto_upgrade=not settings.is_production)
        db = SessionLocal()
        try:
            if settings.is_production:
                disable_known_demo_credentials(db)
            elif settings.seed_demo_data and db.query(models.User).count() == 0:
                from seed_data import seed_database
                seed_database(db)
        finally:
            db.close()
    logger.info("AI-CRMS %s started (env=%s)", APP_VERSION, settings.app_env)
    yield


app = FastAPI(
    title="AI-CRMS API",
    description="Artificial Intelligence Criminal Records Management System",
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.enable_api_docs else None,
    redoc_url="/redoc" if settings.enable_api_docs else None,
    openapi_url="/openapi.json" if settings.enable_api_docs else None,
)

# Middleware order: the last added runs first (outermost).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", "X-Request-ID"],
    expose_headers=["X-Total-Count", "X-Unread-Count", "X-Request-ID", "Content-Disposition"],
)
app.add_middleware(RequestContextMiddleware, hsts=settings.is_production)
if settings.trusted_hosts and "*" not in settings.trusted_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)


# ── Consistent, safe error contracts ──────────────────────────────────────────
def _error(status_code: int, detail, headers=None) -> JSONResponse:
    response = JSONResponse(status_code=status_code, content={"detail": detail, "request_id": current_request_id()})
    for key, value in (headers or {}).items():
        response.headers[key] = value
    return response


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    logger.warning("Integrity error on %s %s: %s", request.method, request.url.path, exc.orig.__class__.__name__)
    return _error(409, "The request conflicts with existing data (duplicate value or a record that is still referenced).")


@app.exception_handler(PermissionError)
async def permission_error_handler(request: Request, exc: PermissionError):
    logger.warning("Blocked write on %s %s: %s", request.method, request.url.path, exc)
    return _error(409, "This record is append-only and cannot be modified or deleted.")


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    # Echo field locations/messages but never the submitted values (may contain PII).
    errors = [{"loc": list(err.get("loc", [])), "msg": err.get("msg"), "type": err.get("type")} for err in exc.errors()]
    return _error(422, errors)


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return _error(500, "Internal server error. Quote the request ID when reporting this problem.")


# Routers
app.include_router(auth.router)
app.include_router(criminals.router)
app.include_router(cases.router)
app.include_router(ai_predictions.router)
app.include_router(admin.router)
app.include_router(admin.directory_router)
app.include_router(gangs.router)
app.include_router(notifications.router)
app.include_router(intelligence.router)


@app.get("/api/health", tags=["health"])
async def health():
    """Liveness: the process is up and serving requests."""
    return {"status": "ok", "service": "AI-CRMS", "version": APP_VERSION}


@app.get("/api/health/ready", tags=["health"])
async def readiness():
    """Readiness: database reachable and schema at the expected revision."""
    checks = {}
    healthy = True
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            revision = current_revision(connection)
        expected = head_revision()
        checks["database"] = "ok"
        checks["schema"] = "ok" if revision == expected else f"revision {revision} != {expected}"
        healthy = revision == expected
    except OperationalError:
        checks["database"] = "unreachable"
        healthy = False
    return JSONResponse(status_code=200 if healthy else 503,
                        content={"status": "ready" if healthy else "not_ready", "checks": checks})
