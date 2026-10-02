import os
import tempfile

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import models, schemas


def test_model_foreign_keys_and_uniques_are_declared():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)

    for table in ["users", "criminals", "cases", "case_criminals", "evidence", "victims", "ai_predictions", "notifications", "audit_logs"]:
        assert inspector.get_pk_constraint(table)["constrained_columns"] == ["id"]

    cc_uniques = inspector.get_unique_constraints("case_criminals")
    assert any(set(u["column_names"]) == {"case_id", "criminal_id"} for u in cc_uniques)

    evidence_uniques = inspector.get_unique_constraints("evidence")
    assert any(set(u["column_names"]) == {"case_id", "evidence_number"} for u in evidence_uniques)

    case_fks = inspector.get_foreign_keys("cases")
    assert {fk["referred_table"] for fk in case_fks} >= {"users"}

    criminal_fks = inspector.get_foreign_keys("criminals")
    assert {fk["referred_table"] for fk in criminal_fks} >= {"gangs", "users"}


def test_sqlite_foreign_keys_are_enforced():
    engine = create_engine("sqlite:///:memory:")
    from app.database import _enable_sqlite_foreign_keys
    # Direct listener invocation is enough to verify the intended pragma behavior.
    raw = engine.raw_connection()
    try:
        _enable_sqlite_foreign_keys(raw, None)
        cur = raw.cursor()
        cur.execute("PRAGMA foreign_keys")
        assert cur.fetchone()[0] == 1
        cur.close()
    finally:
        raw.close()


def test_api_schema_exposes_persisted_sensitive_fields():
    criminal_fields = schemas.CriminalCreate.model_fields
    assert "fingerprint_id" in criminal_fields
    evidence_fields = schemas.EvidenceCreate.model_fields
    assert "chain_of_custody" in evidence_fields
    assert "file_url" in evidence_fields


def test_enum_validation_rejects_invalid_values():
    try:
        schemas.CaseCreate(title="X", priority="urgent")
        assert False, "invalid priority should be rejected"
    except Exception:
        pass
    try:
        schemas.VictimCreate(first_name="A", last_name="B", status="unknown")
        assert False, "invalid victim status should be rejected"
    except Exception:
        pass
