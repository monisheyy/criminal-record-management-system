from dotenv import load_dotenv
load_dotenv()  # Must be first — loads .env before any os.getenv() call

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os

from app.database import engine, Base
from sqlalchemy import inspect, text
from app import models

from app.routers import auth, criminals, cases, ai_predictions, admin, gangs, notifications, intelligence


def ensure_ml_evaluation_columns():
    """Backward-compatible SQLite schema upgrade for ML evaluation metadata."""
    inspector = inspect(engine)
    if "ml_models" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("ml_models")}
    additions = {
        "evaluation_metadata": "JSON",
        "dataset_version": "VARCHAR(50)",
        "evaluation_method": "VARCHAR(120)",
    }
    with engine.begin() as conn:
        for name, sql_type in additions.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE ml_models ADD COLUMN {name} {sql_type}"))


def ensure_password_recovery_columns():
    """Create/upgrade password recovery storage without deleting existing data."""
    inspector = inspect(engine)
    if "password_recovery" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("password_recovery")}
    additions = {"reset_consumed_at": "DATETIME"}
    with engine.begin() as conn:
        for name, sql_type in additions.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE password_recovery ADD COLUMN {name} {sql_type}"))


def ensure_audit_columns():
    """Backward-compatible SQLite schema upgrade for structured audit fields."""
    inspector = inspect(engine)
    if "audit_logs" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("audit_logs")}
    additions = {"role": "VARCHAR(30)", "status": "VARCHAR(20) DEFAULT 'success'", "reason": "TEXT"}
    with engine.begin() as conn:
        for name, sql_type in additions.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE audit_logs ADD COLUMN {name} {sql_type}"))


def ensure_integrity_indexes():
    """Add non-destructive integrity/lookup indexes to existing databases.

    Unique indexes are created only when the existing data has no duplicates.
    We fail startup rather than silently weakening an integrity guarantee if
    legacy data violates the proposed constraint.
    """
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if not {"case_criminals", "evidence", "cases"}.issubset(tables):
        return

    checks = [
        (
            "uq_case_criminal",
            "SELECT case_id, criminal_id, COUNT(*) AS n FROM case_criminals GROUP BY case_id, criminal_id HAVING COUNT(*) > 1",
            "CREATE UNIQUE INDEX uq_case_criminal ON case_criminals(case_id, criminal_id)",
        ),
        (
            "uq_case_evidence_number",
            "SELECT case_id, evidence_number, COUNT(*) AS n FROM evidence GROUP BY case_id, evidence_number HAVING COUNT(*) > 1",
            "CREATE UNIQUE INDEX uq_case_evidence_number ON evidence(case_id, evidence_number)",
        ),
        (
            "uq_cases_fir_number",
            "SELECT fir_number, COUNT(*) AS n FROM cases WHERE fir_number IS NOT NULL GROUP BY fir_number HAVING COUNT(*) > 1",
            "CREATE UNIQUE INDEX uq_cases_fir_number ON cases(fir_number)",
        ),
    ]
    existing_indexes = {i["name"] for table in tables for i in inspect(engine).get_indexes(table)}
    with engine.begin() as conn:
        for name, duplicate_sql, create_sql in checks:
            if name in existing_indexes:
                continue
            duplicate = conn.execute(text(duplicate_sql)).first()
            if duplicate:
                raise RuntimeError(
                    f"Database integrity migration blocked: duplicate data violates {name}: {tuple(duplicate)}"
                )
            conn.execute(text(create_sql))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all tables and upgrade older SQLite schemas without deleting data.
    Base.metadata.create_all(bind=engine)
    ensure_ml_evaluation_columns()
    ensure_audit_columns()
    ensure_password_recovery_columns()
    ensure_integrity_indexes()
    # Auto-seed if empty
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        if db.query(models.User).count() == 0:
            from seed_data import seed_database
            seed_database(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="AI-CRMS API",
    description="Artificial Intelligence Criminal Records Management System",
    version="1.0.0",
    lifespan=lifespan
)

cors_origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173").split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(criminals.router)
app.include_router(cases.router)
app.include_router(ai_predictions.router)
app.include_router(admin.router)
app.include_router(gangs.router)
app.include_router(notifications.router)
app.include_router(intelligence.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "AI-CRMS", "version": "1.0.0"}
