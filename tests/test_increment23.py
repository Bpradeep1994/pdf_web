"""
Increment 23 — security & integration coverage:
  • Authorization / multi-tenant isolation: user B must never reach user A's resources.
  • Conversion + OCR endpoints (wired into the UI, previously untested).
  • Gateway auth resolution: API-key path works; missing/invalid tokens are rejected.

Run on its own (or with the whole suite — conftest.py injects the rate-limit bypass):
    python -m pytest tests/test_increment23.py -q
"""
import time
import httpx
import pytest

BASE = "http://localhost:8000/api/v1"
TIMEOUT = 60
pytestmark = pytest.mark.integration

MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 300 300]/Parent 2 0 R>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"
)
DENIED = (403, 404)   # either is an acceptable "you can't have this"


def _user():
    email = f"i23_{time.time_ns()}@x.com"
    r = httpx.post(f"{BASE}/auth/register",
                   json={"email": email, "password": "TestPass123!", "full_name": "I23"}, timeout=TIMEOUT).json()
    c = httpx.Client(base_url=BASE, headers={"Authorization": f"Bearer {r['access_token']}"}, timeout=TIMEOUT)
    return c


def _doc(c) -> dict:
    return c.post("/documents", files={"file": ("d.pdf", MINIMAL_PDF, "application/pdf")}).json()


@pytest.fixture(scope="module")
def users():
    a, b = _user(), _user()
    yield a, b
    a.close(); b.close()


# ── Authorization / tenant isolation ────────────────────────────────────────
class TestTenantIsolation:
    def test_documents(self, users):
        a, b = users
        doc = _doc(a)["id"]
        assert b.get(f"/documents/{doc}").status_code in DENIED
        assert b.delete(f"/documents/{doc}").status_code in DENIED
        assert b.post(f"/documents/{doc}/edit/watermark", json={"text": "X"}).status_code in DENIED
        assert b.get(f"/documents/{doc}/versions").status_code in DENIED
        assert all(d["id"] != doc for d in b.get("/documents").json())   # not in B's listing

    def test_comments(self, users):
        a, b = users
        doc = _doc(a)["id"]
        a.post(f"/documents/{doc}/comments", json={"content": "secret", "page": 1})
        assert b.get(f"/documents/{doc}/comments").status_code in DENIED
        assert b.post(f"/documents/{doc}/comments", json={"content": "x"}).status_code in DENIED

    def test_signature_requests(self, users):
        a, b = users
        doc = _doc(a)["id"]
        req = a.post("/signatures/requests", json={
            "document_id": doc, "title": "private",
            "fields": [{"signer_email": "s@x.com", "page_number": 1, "x": 1, "y": 1,
                        "width": 10, "height": 10, "field_type": "signature"}]}).json()
        assert b.get(f"/signatures/requests/{req['id']}").status_code in DENIED
        assert all(r["id"] != req["id"] for r in b.get("/signatures/requests").json())

    def test_folders_and_projects_and_keys(self, users):
        a, b = users
        fid = a.post("/folders", json={"name": "A-only"}).json()["id"]
        assert all(f["id"] != fid for f in b.get("/folders").json())
        pid = a.post("/projects", json={"name": "A-proj"}).json()["id"]
        assert all(p["id"] != pid for p in b.get("/projects").json())
        assert b.delete(f"/projects/{pid}").status_code in DENIED
        a.post("/keys", json={"name": "A-key"})
        a_keys = {k["id"] for k in a.get("/keys").json()}
        b_keys = {k["id"] for k in b.get("/keys").json()}
        assert a_keys.isdisjoint(b_keys)


# ── Gateway auth resolution ─────────────────────────────────────────────────
class TestGatewayAuth:
    def test_missing_and_invalid_token_rejected(self):
        assert httpx.get(f"{BASE}/documents", timeout=TIMEOUT).status_code == 401
        assert httpx.get(f"{BASE}/documents",
                         headers={"Authorization": "Bearer not-a-real-token"}, timeout=TIMEOUT).status_code == 401

    def test_api_key_path(self, users):
        a, _ = users
        raw = a.post("/keys", json={"name": "gw"}).json()["key"]
        r = httpx.get(f"{BASE}/documents", headers={"X-API-Key": raw}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text


# ── Conversion ──────────────────────────────────────────────────────────────
class TestConversion:
    def test_convert_pdf_to_txt(self, users):
        a, _ = users
        doc = _doc(a)
        r = a.post("/convert/convert", json={
            "s3_key": doc["s3_key"], "source_format": "pdf",
            "target_format": "txt", "document_id": doc["id"]})
        assert r.status_code == 200, r.text
        assert r.json().get("download_url")

    @pytest.mark.parametrize("fmt", ["docx", "xlsx", "pptx", "png", "txt"])
    def test_convert_office_and_media(self, users, fmt):
        a, _ = users
        doc = _doc(a)
        r = a.post("/convert/convert", json={
            "s3_key": doc["s3_key"], "source_format": "pdf",
            "target_format": fmt, "document_id": doc["id"]})
        assert r.status_code == 200, f"{fmt}: {r.text}"
        assert r.json().get("download_url")

    def test_unsupported_format_rejected(self, users):
        a, _ = users
        doc = _doc(a)
        r = a.post("/convert/convert", json={
            "s3_key": doc["s3_key"], "source_format": "pdf",
            "target_format": "exe", "document_id": doc["id"]})
        assert r.status_code == 400


# ── OCR ─────────────────────────────────────────────────────────────────────
class TestOCR:
    def test_process_and_status(self, users):
        a, _ = users
        doc = _doc(a)
        r = a.post("/ocr/process", json={"document_id": doc["id"], "s3_key": doc["s3_key"], "language": "en"})
        assert r.status_code == 200, r.text
        assert "output_key" in r.json()
        st = a.get(f"/ocr/status/{doc['id']}")
        assert st.status_code == 200
