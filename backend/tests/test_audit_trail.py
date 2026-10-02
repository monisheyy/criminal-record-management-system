from app.utils.audit import create_audit_log

def test_audit_log_redacts_sensitive_metadata():
    class FakeDB:
        def add(self, obj): pass
        def commit(self): pass
        def refresh(self, obj): pass
    log = create_audit_log(FakeDB(), "TEST", user_id=7, username="u", role="admin",
                           resource_type="user", resource_id=8, status="success",
                           reason="test", details={"before": {"email": "secret@example.com", "name": "A"}, "token": "secret"})
    assert log.status == "success"
    assert log.role == "admin"
    assert log.reason == "test"
    assert log.details["before"]["email"] == "[REDACTED]"
    assert log.details["token"] == "[REDACTED]"
