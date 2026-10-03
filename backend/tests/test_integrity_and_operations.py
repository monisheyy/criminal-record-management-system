"""Audit-trail integrity, transactional rollback, migrations and backup/restore."""
import sqlite3
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from app import models
from app.database import Base, SessionLocal


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


# ── Audit trail ────────────────────────────────────────────────────────────────
def test_audit_entries_are_signed_and_correlated_with_request_id(client, admin_token):
    r = client.post("/api/gangs", json={"name": f"Audit Gang {uuid.uuid4().hex[:6]}"}, headers=_bearer(admin_token))
    assert r.status_code == 200
    request_id = r.headers["X-Request-ID"]
    logs = client.get("/api/admin/audit-logs", params={"request_id": request_id}, headers=_bearer(admin_token)).json()
    assert [log["action"] for log in logs] == ["GANG_CREATED"]
    assert logs[0]["role"] == "admin" and logs[0]["username"] == "admin_test"


def test_audit_log_verification_detects_tampering(client, admin_token):
    clean = client.get("/api/admin/audit-logs/verify", headers=_bearer(admin_token)).json()
    assert clean["intact"] is True and clean["checked"] > 0

    db = SessionLocal()
    try:
        target = db.query(models.AuditLog).filter(models.AuditLog.entry_hash.isnot(None)).first()
        # Simulate an attacker with raw DB access who first drops the protective trigger.
        db.execute(text("DROP TRIGGER trg_audit_logs_no_update"))
        db.execute(text("UPDATE audit_logs SET action = 'FORGED' WHERE id = :id"), {"id": target.id})
        db.commit()
        result = client.get("/api/admin/audit-logs/verify", headers=_bearer(admin_token)).json()
        assert result["intact"] is False and target.id in result["tampered_entry_ids"]
    finally:
        original = db.get(models.AuditLog, target.id)
        db.execute(text("UPDATE audit_logs SET action = :a WHERE id = :id"),
                   {"a": "GANG_CREATED" if original.action == "FORGED" else original.action, "id": target.id})
        db.commit()
        db.execute(text("CREATE TRIGGER IF NOT EXISTS trg_audit_logs_no_update BEFORE UPDATE ON audit_logs "
                        "BEGIN SELECT RAISE(ABORT, 'audit_logs is append-only'); END;"))
        db.commit()
        db.close()


def test_audit_log_rows_are_append_only_in_orm_and_database():
    db = SessionLocal()
    try:
        log = db.query(models.AuditLog).first()
        log.reason = "edited"
        with pytest.raises(PermissionError):
            db.commit()
        db.rollback()
        with pytest.raises(Exception, match="append-only"):
            db.execute(text("DELETE FROM audit_logs"))
        db.rollback()
    finally:
        db.close()


def test_failed_case_creation_leaves_no_partial_records(client, admin_token):
    before_cases = SessionLocal().query(models.Case).count()
    r = client.post("/api/cases", json={"title": "Atomicity Check", "crime_type": "Fraud", "criminal_ids": [987654]},
                    headers=_bearer(admin_token))
    assert r.status_code == 404
    db = SessionLocal()
    try:
        assert db.query(models.Case).count() == before_cases
        assert db.query(models.AuditLog).filter(models.AuditLog.action == "CASE_CREATED",
                                                 models.AuditLog.details["title"].as_string() == "Atomicity Check").count() == 0
    finally:
        db.close()


def test_case_closure_requires_reason_and_follows_lifecycle(client, admin_token):
    case = client.post("/api/cases", json={"title": "Lifecycle Case", "crime_type": "Arson"}, headers=_bearer(admin_token)).json()
    assert client.put(f"/api/cases/{case['id']}", json={"status": "closed"}, headers=_bearer(admin_token)).status_code == 422
    closed = client.put(f"/api/cases/{case['id']}", json={"status": "closed", "status_reason": "Charges filed in court"},
                        headers=_bearer(admin_token))
    assert closed.status_code == 200 and closed.json()["closed_at"]
    archived = client.put(f"/api/cases/{case['id']}", json={"status": "archived"}, headers=_bearer(admin_token))
    assert archived.status_code == 200


def test_evidence_custody_log_is_appended_not_overwritten(client, admin_token):
    case = client.post("/api/cases", json={"title": "Custody Case", "crime_type": "Burglary"}, headers=_bearer(admin_token)).json()
    ev = client.post(f"/api/cases/{case['id']}/evidence", json={"type": "Physical", "description": "Crowbar",
                                                              "file_sha256": "a" * 64}, headers=_bearer(admin_token))
    assert ev.status_code == 200, ev.text
    first_log = ev.json()["chain_of_custody"]
    upd = client.put(f"/api/cases/{case['id']}/evidence/{ev.json()['id']}",
                     json={"status": "stored", "custody_note": "Moved to locker 12"}, headers=_bearer(admin_token))
    assert upd.status_code == 200
    log = upd.json()["chain_of_custody"]
    assert log.startswith(first_log) and "Moved to locker 12" in log


def test_deleting_referenced_user_is_refused(client, admin_token):
    officer = SessionLocal().query(models.User).filter_by(username="officer_test").one()
    r = client.delete(f"/api/admin/users/{officer.id}", headers=_bearer(admin_token))
    assert r.status_code == 409 and "Deactivate" in r.json()["detail"]


# ── Migrations ─────────────────────────────────────────────────────────────────
def _alembic_cfg(connection):
    from app.db_bootstrap import _alembic_config
    return _alembic_config(connection)


def test_migrations_upgrade_downgrade_and_match_models(tmp_path):
    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.runtime.migration import MigrationContext

    engine = create_engine(f"sqlite:///{(tmp_path / 'm.db').as_posix()}")
    with engine.begin() as conn:
        cfg = _alembic_cfg(conn)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        assert set(inspect(conn).get_table_names()) <= {"alembic_version"}
        command.upgrade(cfg, "head")
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        assert diff == [], f"models and migrations have drifted: {diff}"


def test_legacy_database_is_adopted_and_data_fixed(tmp_path):
    from alembic import command
    from app.db_bootstrap import head_revision, migrate_database

    path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    with engine.begin() as conn:
        command.upgrade(_alembic_cfg(conn), "0001")
    raw = sqlite3.connect(path)
    raw.execute("DROP TABLE alembic_version")  # looks like a pre-Alembic database
    raw.execute("INSERT INTO criminals (crn, first_name, last_name) VALUES ('CRN1', 'Legacy', 'Person')")
    raw.execute("INSERT INTO ai_predictions (criminal_id, crime_type_confidence, gang_affiliation_probability, "
                "confidence_overall, risk_score, review_status, model_version) VALUES (1, 64.5, 20.0, 50.0, 40, 'confirmed', 'v1')")
    raw.commit()
    raw.close()

    assert migrate_database(engine, allow_auto_upgrade=True) == head_revision()
    with engine.connect() as conn:
        row = conn.execute(text("SELECT crime_type_confidence, confidence_overall FROM ai_predictions")).one()
        assert row == (pytest.approx(0.645), pytest.approx(0.5))
        history = conn.execute(text("SELECT decision, remarks FROM ai_prediction_reviews")).all()
        assert history == [("confirmed", "(legacy review - no reason recorded)")]
        assert conn.execute(text("SELECT first_name FROM criminals")).scalar() == "Legacy"


def test_production_refuses_to_start_on_outdated_schema(tmp_path):
    from app.db_bootstrap import migrate_database

    engine = create_engine(f"sqlite:///{(tmp_path / 'old.db').as_posix()}")
    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        migrate_database(engine, allow_auto_upgrade=False)


# ── Backup / restore drill ─────────────────────────────────────────────────────
def test_backup_verify_and_restore_round_trip(tmp_path):
    from scripts import backup_db

    live = tmp_path / "live.db"
    conn = sqlite3.connect(live)
    conn.execute("CREATE TABLE t (v TEXT)")
    conn.execute("INSERT INTO t VALUES ('before-backup')")
    conn.commit()
    conn.close()

    backup = backup_db.backup(live, tmp_path / "backups")
    assert backup_db.verify(backup)["integrity"] == "ok"

    conn = sqlite3.connect(live)
    conn.execute("DELETE FROM t")
    conn.execute("INSERT INTO t VALUES ('after-incident')")
    conn.commit()
    conn.close()

    backup_db.restore(backup, live)
    conn = sqlite3.connect(live)
    try:
        assert conn.execute("SELECT v FROM t").fetchall() == [("before-backup",)]
    finally:
        conn.close()
    assert list(tmp_path.glob("live.pre-restore-*.db")), "a safety copy must be kept"


def test_corrupted_backup_is_rejected(tmp_path):
    from scripts import backup_db

    live = tmp_path / "live.db"
    sqlite3.connect(live).execute("CREATE TABLE t (v TEXT)").connection.close()
    backup = backup_db.backup(live, tmp_path / "backups")
    with Path(backup).open("ab") as handle:
        handle.write(b"corruption")
    with pytest.raises(RuntimeError, match="checksum"):
        backup_db.restore(backup, live)
