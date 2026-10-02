"""Database schema bootstrap built on Alembic migrations.

* development/test: migrations are applied automatically at start-up.
* production: start-up only *verifies* that the schema is at the latest
  revision; operators apply migrations explicitly (``alembic upgrade head``)
  as a reviewed, backed-up deployment step.

Databases created by earlier versions of AI-CRMS (``create_all`` plus ad-hoc
``ALTER TABLE`` calls, no ``alembic_version`` table) are upgraded to the
baseline shape non-destructively, stamped as revision 0001, then migrated.
"""
from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine

logger = logging.getLogger("ai_crms.db")

BACKEND_DIR = Path(__file__).resolve().parent.parent
BASELINE_REVISION = "0001"


def _alembic_config(connection: Connection) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.attributes["connection"] = connection
    cfg.attributes["skip_logging_config"] = True
    return cfg


def head_revision() -> str:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return ScriptDirectory.from_config(cfg).get_current_head()


def current_revision(connection: Connection):
    return MigrationContext.configure(connection).get_current_revision()


def _upgrade_legacy_schema_to_baseline(connection: Connection) -> None:
    """Bring a pre-Alembic database to the exact baseline (0001) shape.

    These are the additive upgrades the application used to run on every
    start-up. Unique indexes are only created when existing data satisfies
    them; otherwise start-up fails loudly instead of weakening integrity.
    """
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())

    additive_columns = {
        "ml_models": {"evaluation_metadata": "JSON", "dataset_version": "VARCHAR(50)", "evaluation_method": "VARCHAR(120)"},
        "password_recovery": {"reset_consumed_at": "DATETIME"},
        "audit_logs": {"role": "VARCHAR(30)", "status": "VARCHAR(20) DEFAULT 'success'", "reason": "TEXT"},
    }
    for table, columns in additive_columns.items():
        if table not in tables:
            continue
        existing = {col["name"] for col in inspector.get_columns(table)}
        for name, sql_type in columns.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))

    unique_indexes = [
        ("case_criminals", "uq_case_criminal",
         "SELECT case_id, criminal_id FROM case_criminals GROUP BY case_id, criminal_id HAVING COUNT(*) > 1",
         "CREATE UNIQUE INDEX uq_case_criminal ON case_criminals(case_id, criminal_id)"),
        ("evidence", "uq_case_evidence_number",
         "SELECT case_id, evidence_number FROM evidence GROUP BY case_id, evidence_number HAVING COUNT(*) > 1",
         "CREATE UNIQUE INDEX uq_case_evidence_number ON evidence(case_id, evidence_number)"),
        ("cases", "uq_cases_fir_number",
         "SELECT fir_number FROM cases WHERE fir_number IS NOT NULL GROUP BY fir_number HAVING COUNT(*) > 1",
         "CREATE UNIQUE INDEX uq_cases_fir_number ON cases(fir_number)"),
    ]
    for table, name, duplicate_sql, create_sql in unique_indexes:
        if table not in tables:
            continue
        existing_indexes = {i["name"] for i in inspector.get_indexes(table)}
        existing_uniques = {u["name"] for u in inspector.get_unique_constraints(table)}
        if name in existing_indexes or name in existing_uniques:
            continue
        duplicate = connection.execute(text(duplicate_sql)).first()
        if duplicate:
            raise RuntimeError(f"Database upgrade blocked: existing data violates {name}: {tuple(duplicate)}")
        connection.execute(text(create_sql))

    # Missing core tables cannot be recreated safely here (the ORM metadata is
    # the *head* shape, not the baseline), so refuse rather than guess.
    from app.database import Base
    from app import models  # noqa: F401

    baseline_tables = {
        "users", "password_recovery", "gangs", "criminals", "criminal_history", "cases",
        "case_criminals", "evidence", "victims", "ai_predictions", "notifications",
        "audit_logs", "ml_models", "system_settings",
    }
    missing = [Base.metadata.tables[name] for name in baseline_tables if name not in tables]
    if missing:
        raise RuntimeError(
            "Legacy database is missing core tables "
            f"({', '.join(sorted(t.name for t in missing))}); restore it from backup "
            "or start from an empty database."
        )


def migrate_database(engine: Engine, *, allow_auto_upgrade: bool) -> str:
    """Ensure the schema is at head. Returns the resulting revision."""
    head = head_revision()
    with engine.begin() as connection:
        revision = current_revision(connection)
        has_tables = bool(set(inspect(connection).get_table_names()) - {"alembic_version"})

        if revision == head:
            return revision

        if not allow_auto_upgrade:
            raise RuntimeError(
                f"Database schema is at revision {revision!r} but the application requires {head!r}. "
                "Back up the database, then run `alembic upgrade head` before starting the service."
            )

        cfg = _alembic_config(connection)
        if revision is None and has_tables:
            logger.warning("Adopting legacy (pre-Alembic) database: upgrading to baseline and stamping %s", BASELINE_REVISION)
            _upgrade_legacy_schema_to_baseline(connection)
            command.stamp(cfg, BASELINE_REVISION)
        command.upgrade(cfg, "head")
        logger.info("Database migrated to revision %s", head)
        return head
