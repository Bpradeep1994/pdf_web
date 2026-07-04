"""
Increment 19 — production-hardening: account lockout, soft delete, /metrics.
Run against a live stack.
"""
import time
import httpx
import pytest

BASE    = "http://localhost:8000/api/v1"
ROOT    = "http://localhost:8000"
TIMEOUT = 30
pytestmark = pytest.mark.integration

MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 200 200]/Parent 2 0 R>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"
)


def _hdr(t): return {"Authorization": f"Bearer {t}"}


class TestAccountLockout:
    def test_lockout_after_repeated_failures(self):
        email = f"lock_{time.time_ns()}@x.com"
        httpx.post(f"{BASE}/auth/register",
                   json={"email": email, "password": "TestPass123!", "full_name": "L"}, timeout=TIMEOUT).raise_for_status()
        # 5 wrong-password attempts → then locked (429) even though we now use the RIGHT password
        codes = []
        for _ in range(5):
            codes.append(httpx.post(f"{BASE}/auth/login",
                         json={"email": email, "password": "WRONG"}, timeout=TIMEOUT).status_code)
        assert all(c == 401 for c in codes), codes
        locked = httpx.post(f"{BASE}/auth/login",
                            json={"email": email, "password": "TestPass123!"}, timeout=TIMEOUT)
        assert locked.status_code == 429, locked.text


class TestSoftDelete:
    def test_delete_is_soft_and_hidden(self):
        t = httpx.post(f"{BASE}/auth/register",
                       json={"email": f"sd_{time.time_ns()}@x.com", "password": "TestPass123!", "full_name": "S"},
                       timeout=TIMEOUT).json()["access_token"]
        doc = httpx.post(f"{BASE}/documents", headers=_hdr(t),
                         files={"file": ("d.pdf", MINIMAL_PDF, "application/pdf")}, timeout=TIMEOUT).json()["id"]
        assert httpx.delete(f"{BASE}/documents/{doc}", headers=_hdr(t), timeout=TIMEOUT).status_code == 204
        # gone from listing and from GET (404)
        assert httpx.get(f"{BASE}/documents/{doc}", headers=_hdr(t), timeout=TIMEOUT).status_code == 404
        listing = httpx.get(f"{BASE}/documents", headers=_hdr(t), timeout=TIMEOUT).json()
        assert all(d["id"] != doc for d in listing)


class TestMetrics:
    def test_metrics_endpoint(self):
        r = httpx.get(f"{ROOT}/metrics", timeout=TIMEOUT)
        assert r.status_code == 200
        assert "http_request" in r.text or "process_" in r.text
