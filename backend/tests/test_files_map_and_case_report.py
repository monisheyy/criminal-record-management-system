"""Offender photos, evidence files, the incident map and the FIR-style case report."""
import hashlib
import io
import struct
import zlib

from pypdf import PdfReader

from app import models
from app.utils import file_store, geo


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def png_bytes(r=200, g=40, b=40, size=4):
    """A real (decodable) PNG, so the PDF report can embed it."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + bytes([r, g, b]) * size for _ in range(size))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def make_criminal(client, token, first="Photo", last="Subject"):
    r = client.post("/api/criminals", json={"first_name": first, "last_name": last, "crime_type": "Robbery",
                                            "prior_convictions": 1}, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def make_case(client, token, title="Files case", location="Dongri, Mumbai", **extra):
    r = client.post("/api/cases", json={"title": title, "crime_type": "Robbery", "location": location, **extra},
                    headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def add_evidence(client, token, case_id, **extra):
    r = client.post(f"/api/cases/{case_id}/evidence", json={"description": "Seized phone", "type": "digital", **extra},
                    headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def upload(client, url, token, data, name="file.bin", method="put"):
    return getattr(client, method)(url, files={"file": (name, data, "application/octet-stream")}, headers=auth(token))


def officer_id(client, token):
    return client.get("/api/auth/me", headers=auth(token)).json()["id"]


# ── Offender photos ──────────────────────────────────────────────────────────
def test_photo_upload_round_trip_and_audit(client, clerk_token, admin_token, db):
    c = make_criminal(client, admin_token)
    image = png_bytes()
    r = upload(client, f"/api/criminals/{c['id']}/photo", clerk_token, image, "mugshot.png")
    assert r.status_code == 200, r.text
    sha = hashlib.sha256(image).hexdigest()
    assert r.json()["photo_sha256"] == sha

    r = client.get(f"/api/criminals/{c['id']}/photo", headers=auth(admin_token))
    assert r.status_code == 200
    assert r.content == image and r.headers["content-type"] == "image/png"

    log = db.query(models.AuditLog).filter_by(action="CRIMINAL_PHOTO_UPLOADED", resource_id=c["id"]).one()
    assert log.details["sha256"] == sha and log.details["size_bytes"] == len(image)
    history = client.get(f"/api/criminals/{c['id']}/history", headers=auth(admin_token)).json()
    assert any(h["event_type"] == "photo_updated" for h in history)


def test_photo_type_is_decided_by_content_not_name(client, admin_token):
    c = make_criminal(client, admin_token, "Sniff", "Test")
    r = upload(client, f"/api/criminals/{c['id']}/photo", admin_token, b"<svg onload=alert(1)>", "photo.png")
    assert r.status_code == 415
    r = upload(client, f"/api/criminals/{c['id']}/photo", admin_token, PDF, "photo.jpg")
    assert r.status_code == 415, "a PDF is not an acceptable photo"
    r = upload(client, f"/api/criminals/{c['id']}/photo", admin_token, b"", "empty.png")
    assert r.status_code == 422


def test_photo_size_limit(client, admin_token, monkeypatch):
    c = make_criminal(client, admin_token, "Big", "Photo")
    monkeypatch.setattr(file_store, "MAX_PHOTO_BYTES", 100)
    r = upload(client, f"/api/criminals/{c['id']}/photo", admin_token, png_bytes(size=40), "big.png")
    assert r.status_code == 413
    assert not any(p.name.startswith(".incoming-") for p in file_store.UPLOAD_DIR.iterdir())


def test_tampered_photo_is_refused_and_audited(client, admin_token, db):
    c = make_criminal(client, admin_token, "Tamper", "Photo")
    image = png_bytes(10, 200, 10)
    sha = upload(client, f"/api/criminals/{c['id']}/photo", admin_token, image, "p.png").json()["photo_sha256"]
    path = file_store.UPLOAD_DIR / sha
    path.chmod(0o640)
    path.write_bytes(image + b"tampered")
    try:
        r = client.get(f"/api/criminals/{c['id']}/photo", headers=auth(admin_token))
        assert r.status_code == 409
        assert db.query(models.AuditLog).filter_by(action="FILE_INTEGRITY_FAILURE", resource_id=c["id"]).count() == 1
    finally:
        path.write_bytes(image)


def test_photo_removal_needs_reason_and_keeps_file(client, admin_token):
    c = make_criminal(client, admin_token, "Remove", "Photo")
    image = png_bytes(1, 2, 3)
    sha = upload(client, f"/api/criminals/{c['id']}/photo", admin_token, image, "p.png").json()["photo_sha256"]
    assert client.delete(f"/api/criminals/{c['id']}/photo", headers=auth(admin_token)).status_code == 422
    r = client.delete(f"/api/criminals/{c['id']}/photo", params={"reason": "Wrong person photographed"},
                      headers=auth(admin_token))
    assert r.status_code == 200 and r.json()["photo_sha256"] is None
    assert client.get(f"/api/criminals/{c['id']}/photo", headers=auth(admin_token)).status_code == 404
    assert (file_store.UPLOAD_DIR / sha).exists()


def test_photo_requires_authentication(client, admin_token):
    c = make_criminal(client, admin_token, "Anon", "Photo")
    assert client.get(f"/api/criminals/{c['id']}/photo").status_code == 401
    r = client.put(f"/api/criminals/{c['id']}/photo", files={"file": ("p.png", png_bytes(), "image/png")})
    assert r.status_code == 401


# ── Evidence files ───────────────────────────────────────────────────────────
def test_evidence_file_is_write_once_and_downloadable(client, officer_token, clerk_token, db):
    case = make_case(client, officer_token, "Evidence upload case")
    ev = add_evidence(client, officer_token, case["id"])
    url = f"/api/cases/{case['id']}/evidence/{ev['id']}/file"

    r = upload(client, url, officer_token, PDF, "../../etc/seizure memo.pdf", method="post")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["file_sha256"] == hashlib.sha256(PDF).hexdigest()
    assert body["file_content_type"] == "application/pdf"
    assert body["file_name"] == "seizure memo.pdf"
    assert body["file_size"] == len(PDF)
    assert "File seizure memo.pdf stored" in body["chain_of_custody"]

    assert upload(client, url, officer_token, png_bytes(), "other.png", method="post").status_code == 409

    r = client.get(url, headers=auth(clerk_token))
    assert r.status_code == 200 and r.content == PDF
    assert r.headers["x-content-sha256"] == body["file_sha256"]
    assert 'filename="seizure memo.pdf"' in r.headers["content-disposition"]
    assert db.query(models.AuditLog).filter_by(action="EVIDENCE_FILE_ACCESSED", resource_id=ev["id"]).count() == 1


def test_evidence_upload_must_match_hash_recorded_at_collection(client, admin_token):
    case = make_case(client, admin_token, "Recorded hash case")
    recorded = hashlib.sha256(PDF).hexdigest()
    ev = add_evidence(client, admin_token, case["id"], file_sha256=recorded)
    url = f"/api/cases/{case['id']}/evidence/{ev['id']}/file"
    assert upload(client, url, admin_token, png_bytes(), "wrong.png", method="post").status_code == 422
    assert upload(client, url, admin_token, PDF, "right.pdf", method="post").status_code == 200


def test_evidence_file_respects_case_assignment(client, admin_token, officer_token, clerk_token, db):
    other = db.query(models.User).filter_by(username="officer_other").first()
    if not other:
        from app.security import get_password_hash
        other = models.User(username="officer_other", email="other@test.com", full_name="Other Officer",
                            hashed_password=get_password_hash("x" * 12), role=models.UserRole.investigating_officer)
        db.add(other)
        db.commit()
    case = make_case(client, admin_token, "Someone else's case")
    assert client.post(f"/api/cases/{case['id']}/assign", json={"officer_id": other.id},
                       headers=auth(admin_token)).status_code == 200
    ev = add_evidence(client, admin_token, case["id"])
    url = f"/api/cases/{case['id']}/evidence/{ev['id']}/file"
    assert upload(client, url, officer_token, PDF, "x.pdf", method="post").status_code == 403
    assert upload(client, url, clerk_token, PDF, "x.pdf", method="post").status_code == 403
    assert client.get(url, headers=auth(officer_token)).status_code == 403
    assert client.get(url, headers=auth(admin_token)).status_code == 404


# ── Incident map ─────────────────────────────────────────────────────────────
def test_geo_resolves_localities_cities_and_rejects_unknown_places():
    loc = geo.resolve("Dongri, Mumbai", seed="A")
    assert loc["precision"] == "locality" and loc["city"] == "Mumbai"
    assert abs(loc["lat"] - 18.962) < 0.01 and abs(loc["lng"] - 72.836) < 0.01
    city = geo.resolve("Somewhere unknown, Pune", seed="B")
    assert city["precision"] == "city" and city["city"] == "Pune"
    assert geo.resolve("Atlantis") is None and geo.resolve("") is None and geo.resolve(None) is None
    assert geo.resolve("Dongri, Mumbai", seed="A") == loc, "positions must be stable between requests"
    assert geo.resolve("Dongri, Mumbai", seed="C") != loc, "cases in one place must not stack exactly"


def test_incident_map_places_cases_and_counts_unmapped(client, admin_token, clerk_token):
    mapped = make_case(client, admin_token, "Map: Bengaluru case", "Koramangala, Bengaluru")
    unmapped = make_case(client, admin_token, "Map: unknown place", "Middle of nowhere")
    for token in (admin_token, clerk_token):
        r = client.get("/api/intelligence/incident-map", headers=auth(token))
        assert r.status_code == 200, r.text
        data = r.json()
        point = next(i for i in data["incidents"] if i["case_id"] == mapped["id"])
        assert point["city"] == "Bengaluru" and point["precision"] == "locality"
        assert all(i["case_id"] != unmapped["id"] for i in data["incidents"])
        assert data["unmapped"] >= 1
        assert any(c["city"] == "Bengaluru" and c["count"] >= 1 for c in data["by_city"])


def test_incident_map_hides_other_officers_cases(client, admin_token, officer_token, db):
    other = db.query(models.User).filter(models.User.role == models.UserRole.investigating_officer,
                                         models.User.username != "officer_test").first()
    if other is None:
        from app.security import get_password_hash
        other = models.User(username="officer_map", email="map@test.com", full_name="Map Officer",
                            hashed_password=get_password_hash("x" * 12), role=models.UserRole.investigating_officer)
        db.add(other)
        db.commit()
    case = make_case(client, admin_token, "Map: assigned elsewhere", "Park Street, Kolkata")
    client.post(f"/api/cases/{case['id']}/assign", json={"officer_id": other.id}, headers=auth(admin_token))
    ids = {i["case_id"] for i in client.get("/api/intelligence/incident-map", headers=auth(officer_token)).json()["incidents"]}
    assert case["id"] not in ids
    ids = {i["case_id"] for i in client.get("/api/intelligence/incident-map", headers=auth(admin_token)).json()["incidents"]}
    assert case["id"] in ids


def test_incident_map_filters(client, admin_token):
    case = make_case(client, admin_token, "Map: filter", "Naroda, Ahmedabad")
    r = client.get("/api/intelligence/incident-map", params={"status": "closed"}, headers=auth(admin_token))
    assert all(i["status"] == "closed" for i in r.json()["incidents"])
    assert case["id"] not in {i["case_id"] for i in r.json()["incidents"]}
    assert client.get("/api/intelligence/incident-map", params={"status": "bogus"},
                      headers=auth(admin_token)).status_code == 422


# ── FIR-style case report ────────────────────────────────────────────────────
def _pdf_text(content: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(content)).pages)


def test_case_report_is_fir_style_with_photos_hashes_and_review(client, admin_token, clerk_token):
    criminal = make_criminal(client, admin_token, "Report", "Accused")
    upload(client, f"/api/criminals/{criminal['id']}/photo", admin_token, png_bytes(), "p.png")
    case = make_case(client, admin_token, "Report: Hawala probe", "Zaveri Bazaar, Mumbai",
                     description="Cash couriers moved funds through shell firms.",
                     complainant_name="Ramesh Iyer", fir_station="L.T. Marg Police Station")
    client.post(f"/api/cases/{case['id']}/criminals", json={"criminal_id": criminal["id"], "role": "accused"},
                headers=auth(admin_token))
    ev = add_evidence(client, admin_token, case["id"])
    upload(client, f"/api/cases/{case['id']}/evidence/{ev['id']}/file", admin_token, PDF, "ledger.pdf", method="post")

    r = client.get(f"/api/cases/{case['id']}/report", headers=auth(admin_token))
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    text = _pdf_text(r.content)
    for expected in ("POLICE STATION AND FIR", "OCCURRENCE OF OFFENCE", "COMPLAINANT / INFORMANT",
                     "DETAILS OF KNOWN / SUSPECTED ACCUSED", "PROPERTY / EVIDENCE SEIZED", "BRIEF FACTS OF THE CASE",
                     "AI DECISION SUPPORT AND HUMAN REVIEW", "Report Accused", "Ramesh Iyer",
                     "Cash couriers moved funds", "Stored file: ledger.pdf", "Signature of investigating officer",
                     "not a legal FIR"):
        assert expected in text, expected
    assert hashlib.sha256(PDF).hexdigest()[:20] in text.replace("\n", "")

    clerk_text = _pdf_text(client.get(f"/api/cases/{case['id']}/report", headers=auth(clerk_token)).content)
    assert "AI DECISION SUPPORT" not in clerk_text, "clerical exports omit AI output"


def test_case_report_survives_minimal_case_data():
    from app.utils.fir_report import generate_case_report
    content = generate_case_report({"case_number": "CASE/1", "status": "open"})
    assert "No accused persons are linked" in _pdf_text(content)
    broken_photo = {"criminals": [{"criminal": {"first_name": "A", "last_name": "B", "photo_bytes": b"\x89PNG broken"}}]}
    assert generate_case_report(broken_photo).startswith(b"%PDF")
