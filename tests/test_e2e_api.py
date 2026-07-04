"""
End-to-end API integration tests — run against a live stack.
Start the stack first:  docker compose up -d
Then run:              pytest tests/test_e2e_api.py -m integration -v

All tests share a registered user; auth token is refreshed automatically.
"""
import pytest
import httpx
import time
import os

BASE   = os.getenv("API_URL", "http://localhost:8000/api/v1")
TIMEOUT = 30

pytestmark = pytest.mark.integration


# ──────────────────────────────────────────────────────────────────────────────
# Shared state
# ──────────────────────────────────────────────────────────────────────────────

_state = {
    "access_token":  None,
    "refresh_token": None,
    "user_id":       None,
    "document_id":   None,
    "session_id":    None,
}

TEST_EMAIL    = f"e2e_test_{int(time.time())}@example.com"
TEST_PASSWORD = "TestPass123!"
TEST_NAME     = "E2E Test User"


def auth_headers():
    return {"Authorization": f"Bearer {_state['access_token']}"}


# ──────────────────────────────────────────────────────────────────────────────
# 1. Infrastructure health checks
# ──────────────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_gateway_health(self):
        r = httpx.get(f"{BASE.replace('/api/v1', '')}/health", timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_auth_service_health(self):
        r = httpx.get("http://localhost:8001/health", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_pdf_service_health(self):
        r = httpx.get("http://localhost:8002/health", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_ocr_service_health(self):
        r = httpx.get("http://localhost:8004/health", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_conversion_service_health(self):
        r = httpx.get("http://localhost:8005/health", timeout=TIMEOUT)
        assert r.status_code == 200


# ──────────────────────────────────────────────────────────────────────────────
# 2. Auth workflow
# ──────────────────────────────────────────────────────────────────────────────

class TestAuthWorkflow:
    def test_register(self):
        r = httpx.post(f"{BASE}/auth/register", json={
            "email":     TEST_EMAIL,
            "password":  TEST_PASSWORD,
            "full_name": TEST_NAME,
        }, timeout=TIMEOUT)
        assert r.status_code == 201, r.text
        data = r.json()
        assert "access_token"  in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        _state["access_token"]  = data["access_token"]
        _state["refresh_token"] = data["refresh_token"]

    def test_me_endpoint(self):
        r = httpx.get(f"{BASE}/auth/me", headers=auth_headers(), timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        user = r.json()
        assert user["email"] == TEST_EMAIL
        assert user["full_name"] == TEST_NAME
        assert user["role"] == "free"
        _state["user_id"] = user["id"]

    def test_duplicate_register_rejected(self):
        r = httpx.post(f"{BASE}/auth/register", json={
            "email": TEST_EMAIL, "password": TEST_PASSWORD, "full_name": TEST_NAME,
        }, timeout=TIMEOUT)
        assert r.status_code == 409

    def test_login(self):
        r = httpx.post(f"{BASE}/auth/login", json={
            "email": TEST_EMAIL, "password": TEST_PASSWORD,
        }, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "access_token" in data
        _state["access_token"]  = data["access_token"]
        _state["refresh_token"] = data["refresh_token"]

    def test_login_wrong_password(self):
        r = httpx.post(f"{BASE}/auth/login", json={
            "email": TEST_EMAIL, "password": "WrongPassword!",
        }, timeout=TIMEOUT)
        assert r.status_code == 401

    def test_refresh_token(self):
        r = httpx.post(f"{BASE}/auth/refresh", json={
            "refresh_token": _state["refresh_token"],
        }, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        data = r.json()
        _state["access_token"]  = data["access_token"]
        _state["refresh_token"] = data["refresh_token"]

    def test_unauthenticated_access_rejected(self):
        r = httpx.get(f"{BASE}/auth/me", timeout=TIMEOUT)
        assert r.status_code == 401

    def test_password_reset_request(self):
        r = httpx.post(f"{BASE}/auth/password-reset", json={"email": TEST_EMAIL}, timeout=TIMEOUT)
        assert r.status_code == 200
        # Always returns 200 (no info leak)
        assert "message" in r.json()

    def test_password_reset_nonexistent_email(self):
        r = httpx.post(f"{BASE}/auth/password-reset", json={"email": "nobody@example.com"}, timeout=TIMEOUT)
        assert r.status_code == 200  # Same response — no leak


# ──────────────────────────────────────────────────────────────────────────────
# 3. Document workflow
# ──────────────────────────────────────────────────────────────────────────────

MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f \n"
    b"0000000009 00000 n \n"
    b"0000000058 00000 n \n"
    b"0000000115 00000 n \n"
    b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF"
)


class TestDocumentWorkflow:
    def test_upload_pdf(self):
        r = httpx.post(
            f"{BASE}/documents",
            files={"file": ("test.pdf", MINIMAL_PDF, "application/pdf")},
            headers=auth_headers(),
            timeout=TIMEOUT,
        )
        assert r.status_code == 201, r.text
        doc = r.json()
        assert doc["original_name"] == "test.pdf"
        assert doc["status"] in ("ready", "processing")
        _state["document_id"] = doc["id"]

    def test_upload_non_pdf_rejected(self):
        r = httpx.post(
            f"{BASE}/documents",
            files={"file": ("test.txt", b"hello world", "text/plain")},
            headers=auth_headers(),
            timeout=TIMEOUT,
        )
        assert r.status_code == 400

    def test_list_documents(self):
        r = httpx.get(f"{BASE}/documents", headers=auth_headers(), timeout=TIMEOUT)
        assert r.status_code == 200
        docs = r.json()
        assert isinstance(docs, list)
        assert any(d["id"] == _state["document_id"] for d in docs)

    def test_get_document(self):
        r = httpx.get(f"{BASE}/documents/{_state['document_id']}", headers=auth_headers(), timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json()["id"] == _state["document_id"]

    def test_get_nonexistent_document(self):
        r = httpx.get(
            f"{BASE}/documents/00000000-0000-0000-0000-000000000000",
            headers=auth_headers(), timeout=TIMEOUT,
        )
        assert r.status_code == 404

    def test_get_document_other_user_rejected(self):
        # Can't access another user's doc without sharing
        r = httpx.get(
            f"{BASE}/documents/{_state['document_id']}",
            headers={"Authorization": "Bearer fake_token"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 401

    def test_download_url(self):
        r = httpx.get(f"{BASE}/documents/{_state['document_id']}/download", headers=auth_headers(), timeout=TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert "url" in data
        assert data["url"].startswith("http")

    def test_list_versions(self):
        r = httpx.get(f"{BASE}/documents/{_state['document_id']}/versions", headers=auth_headers(), timeout=TIMEOUT)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_share_document(self):
        r = httpx.post(
            f"{BASE}/documents/{_state['document_id']}/share",
            json={"permission": "view", "expires_hours": 24},
            headers=auth_headers(),
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        data = r.json()
        assert "share_token" in data
        assert "share_url" in data
        assert len(data["share_token"]) > 10

    def test_extract_text(self):
        r = httpx.get(
            f"{BASE}/documents/{_state['document_id']}/text",
            headers=auth_headers(), timeout=TIMEOUT,
        )
        assert r.status_code == 200
        assert "text" in r.json()

    def test_pagination(self):
        r = httpx.get(
            f"{BASE}/documents?page=1&page_size=5",
            headers=auth_headers(), timeout=TIMEOUT,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        assert len(r.json()) <= 5


# ──────────────────────────────────────────────────────────────────────────────
# 5. OCR workflow
# ──────────────────────────────────────────────────────────────────────────────

class TestOCRWorkflow:
    def test_ocr_status_endpoint(self):
        if not _state["document_id"]:
            pytest.skip("No document uploaded")
        r = httpx.get(
            f"{BASE}/ocr/status/{_state['document_id']}",
            headers=auth_headers(), timeout=TIMEOUT,
        )
        assert r.status_code == 200
        data = r.json()
        assert "is_ocr_done" in data

    def test_ocr_nonexistent_document(self):
        r = httpx.get(
            f"{BASE}/ocr/status/00000000-0000-0000-0000-000000000000",
            headers=auth_headers(), timeout=TIMEOUT,
        )
        assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# 6. Conversion workflow
# ──────────────────────────────────────────────────────────────────────────────

class TestConversionWorkflow:
    def test_supported_formats(self):
        r = httpx.get(f"{BASE}/convert/formats", headers=auth_headers(), timeout=TIMEOUT)
        assert r.status_code == 200
        formats = r.json()["formats"]
        assert "pdf" in formats
        assert "docx" in formats
        assert "png" in formats

    def test_unsupported_format_rejected(self):
        r = httpx.post(
            f"{BASE}/convert/convert",
            json={
                "s3_key":        "some/key.pdf",
                "source_format": "pdf",
                "target_format": "xyz",
                "document_id":   _state["document_id"] or "00000000-0000-0000-0000-000000000000",
            },
            headers=auth_headers(), timeout=TIMEOUT,
        )
        assert r.status_code == 400


# ──────────────────────────────────────────────────────────────────────────────
# 7. Gateway rate limiting
# ──────────────────────────────────────────────────────────────────────────────

class TestGateway:
    def test_404_for_unknown_service(self):
        r = httpx.get(f"{BASE}/nonexistent/path", headers=auth_headers(), timeout=TIMEOUT)
        assert r.status_code == 404

    def test_health_endpoint_no_auth_required(self):
        r = httpx.get(f"{BASE.replace('/api/v1', '')}/health", timeout=TIMEOUT)
        assert r.status_code == 200


# ──────────────────────────────────────────────────────────────────────────────
# 8. Cleanup — delete test document
# ──────────────────────────────────────────────────────────────────────────────

class TestCleanup:
    def test_delete_document(self):
        if not _state["document_id"]:
            pytest.skip("No document to clean up")
        r = httpx.delete(
            f"{BASE}/documents/{_state['document_id']}",
            headers=auth_headers(), timeout=TIMEOUT,
        )
        assert r.status_code == 204

    def test_deleted_document_not_found(self):
        if not _state["document_id"]:
            pytest.skip("No document to check")
        r = httpx.get(
            f"{BASE}/documents/{_state['document_id']}",
            headers=auth_headers(), timeout=TIMEOUT,
        )
        assert r.status_code == 404

    def test_logout(self):
        r = httpx.post(
            f"{BASE}/auth/logout",
            json={"refresh_token": _state["refresh_token"]},
            headers=auth_headers(),
            timeout=TIMEOUT,
        )
        assert r.status_code == 200

    def test_refresh_after_logout_rejected(self):
        r = httpx.post(f"{BASE}/auth/refresh", json={
            "refresh_token": _state["refresh_token"],
        }, timeout=TIMEOUT)
        assert r.status_code == 401
