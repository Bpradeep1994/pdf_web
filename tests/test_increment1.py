"""
Increment 1 tests — security hardening + Phase 1 completion (split/compress/upload).
Run against a live stack:  pytest tests/test_increment1.py -v
"""
import time
import httpx
import pytest

BASE    = "http://localhost:8000/api/v1"
TIMEOUT = 30
pytestmark = pytest.mark.integration

MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f \n"
    b"0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n"
    b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF"
)


def _register():
    email = f"inc1_{time.time_ns()}@example.com"
    r = httpx.post(f"{BASE}/auth/register",
                   json={"email": email, "password": "TestPass123!", "full_name": "Inc1"},
                   timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["access_token"]


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


def _upload(token):
    r = httpx.post(f"{BASE}/documents",
                   headers=_hdr(token),
                   files={"file": ("test.pdf", MINIMAL_PDF, "application/pdf")},
                   timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["id"]


@pytest.fixture(scope="module")
def token():
    return _register()


@pytest.fixture(scope="module")
def doc_id(token):
    return _upload(token)


# ── Security ──────────────────────────────────────────────────────────────────

class TestSecurity:
    def test_no_auth_is_401(self):
        assert httpx.get(f"{BASE}/documents", timeout=TIMEOUT).status_code == 401

    def test_malformed_bearer_is_401_not_500(self):
        # Regression: malformed/garbage Bearer tokens used to 500 at the gateway;
        # the gateway now returns a clean 401 for any invalid credential.
        # (httpx won't send a literal empty "Bearer " value, so use garbage.)
        for bad in ("Bearer x", "Bearer not.a.jwt", "Bearer abc.def.ghi"):
            r = httpx.get(f"{BASE}/documents", headers={"Authorization": bad}, timeout=TIMEOUT)
            assert r.status_code == 401, f"{bad!r} -> {r.status_code}"

    def test_tampered_jwt_rejected(self, token):
        bad = token[:-3] + "zzz"
        r = httpx.get(f"{BASE}/auth/me", headers=_hdr(bad), timeout=TIMEOUT)
        assert r.status_code == 401

    def test_sql_injection_login_rejected(self):
        r = httpx.post(f"{BASE}/auth/login",
                       json={"email": "a@b.com", "password": "x' OR '1'='1"}, timeout=TIMEOUT)
        assert r.status_code == 401

    def test_idor_other_user_cannot_read_doc(self, token, doc_id):
        other = _register()
        r = httpx.get(f"{BASE}/documents/{doc_id}", headers=_hdr(other), timeout=TIMEOUT)
        assert r.status_code == 404

    def test_idor_other_user_cannot_convert_doc(self, token, doc_id):
        other = _register()
        r = httpx.post(f"{BASE}/convert/convert",
                       headers=_hdr(other),
                       json={"document_id": doc_id, "source_format": "pdf", "target_format": "txt"},
                       timeout=TIMEOUT)
        assert r.status_code == 404


# ── Upload validation ───────────────────────────────────────────────────────────

class TestUploadValidation:
    def test_fake_pdf_content_rejected(self, token):
        # Real magic-byte check: content isn't a PDF even though MIME says so.
        r = httpx.post(f"{BASE}/documents", headers=_hdr(token),
                       files={"file": ("evil.pdf", b"not a pdf at all", "application/pdf")},
                       timeout=TIMEOUT)
        assert r.status_code == 400

    def test_empty_file_rejected(self, token):
        r = httpx.post(f"{BASE}/documents", headers=_hdr(token),
                       files={"file": ("empty.pdf", b"", "application/pdf")},
                       timeout=TIMEOUT)
        assert r.status_code == 400


# ── Phase 1: Split / Compress ────────────────────────────────────────────────────

class TestSplitCompress:
    def test_split_each_page(self, token, doc_id):
        r = httpx.post(f"{BASE}/documents/{doc_id}/split", headers=_hdr(token),
                       json={"ranges": None}, timeout=TIMEOUT)
        assert r.status_code == 201
        parts = r.json()
        assert isinstance(parts, list) and len(parts) >= 1
        assert parts[0]["id"] != doc_id

    def test_split_invalid_range_rejected(self, token, doc_id):
        r = httpx.post(f"{BASE}/documents/{doc_id}/split", headers=_hdr(token),
                       json={"ranges": [[1, 999]]}, timeout=TIMEOUT)
        assert r.status_code == 400

    def test_compress_returns_document(self, token, doc_id):
        r = httpx.post(f"{BASE}/documents/{doc_id}/compress", headers=_hdr(token), timeout=TIMEOUT)
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == doc_id
        assert "s3_key" in body


# ── Admin RBAC ───────────────────────────────────────────────────────────────────

class TestAdmin:
    def test_admin_requires_auth(self):
        assert httpx.get(f"{BASE}/admin/stats", timeout=TIMEOUT).status_code == 401

    def test_admin_forbidden_for_non_admin(self, token):
        # A freshly-registered user has role=free → must be denied.
        r = httpx.get(f"{BASE}/admin/stats", headers=_hdr(token), timeout=TIMEOUT)
        assert r.status_code == 403
        r2 = httpx.get(f"{BASE}/admin/users", headers=_hdr(token), timeout=TIMEOUT)
        assert r2.status_code == 403


# ── Conversion (owner) ───────────────────────────────────────────────────────────

class TestConversion:
    def test_owner_can_convert_to_txt(self, token, doc_id):
        r = httpx.post(f"{BASE}/convert/convert", headers=_hdr(token),
                       json={"document_id": doc_id, "source_format": "pdf", "target_format": "txt"},
                       timeout=TIMEOUT)
        assert r.status_code == 200
        body = r.json()
        assert body["download_url"].startswith("http")
        # presigned URL must be browser-reachable (localhost), not internal minio host
        assert "minio:9000" not in body["download_url"]
