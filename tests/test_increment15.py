"""
Increment 15 — email verification + replace-pages (+ storage analytics field).
Run against a live stack.
"""
import time
import httpx
import pytest

BASE    = "http://localhost:8000/api/v1"
TIMEOUT = 30
pytestmark = pytest.mark.integration

ONE_PAGE = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 200 200]/Parent 2 0 R>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF"
)
THREE_PAGE = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R 4 0 R 5 0 R]/Count 3>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 200 200]/Parent 2 0 R>>endobj\n"
    b"4 0 obj<</Type/Page/MediaBox[0 0 200 200]/Parent 2 0 R>>endobj\n"
    b"5 0 obj<</Type/Page/MediaBox[0 0 200 200]/Parent 2 0 R>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF"
)


def _reg():
    return httpx.post(f"{BASE}/auth/register",
                      json={"email": f"ev_{time.time_ns()}@x.com", "password": "TestPass123!", "full_name": "EV"},
                      timeout=TIMEOUT).json()["access_token"]


def _hdr(t): return {"Authorization": f"Bearer {t}"}


def _upload(t, data):
    return httpx.post(f"{BASE}/documents", headers=_hdr(t),
                      files={"file": ("d.pdf", data, "application/pdf")}, timeout=TIMEOUT).json()["id"]


class TestEmailVerification:
    def test_flow(self):
        t = _reg()
        assert httpx.get(f"{BASE}/auth/me", headers=_hdr(t), timeout=TIMEOUT).json()["is_verified"] is False
        resend = httpx.post(f"{BASE}/auth/resend-verification", headers=_hdr(t), timeout=TIMEOUT)
        assert resend.status_code == 200
        token = resend.json()["token"]   # dev-only convenience
        assert httpx.post(f"{BASE}/auth/verify-email", json={"token": token}, timeout=TIMEOUT).status_code == 200
        assert httpx.get(f"{BASE}/auth/me", headers=_hdr(t), timeout=TIMEOUT).json()["is_verified"] is True

    def test_bad_token(self):
        assert httpx.post(f"{BASE}/auth/verify-email", json={"token": "nope"}, timeout=TIMEOUT).status_code == 400


class TestReplacePage:
    def test_replace(self):
        t = _reg()
        target = _upload(t, THREE_PAGE)
        source = _upload(t, ONE_PAGE)
        r = httpx.post(f"{BASE}/documents/{target}/pages/replace", headers=_hdr(t),
                       json={"page": 2, "source_document_id": source, "source_page": 1}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text

    def test_replace_bad_page(self):
        t = _reg()
        target = _upload(t, THREE_PAGE)
        source = _upload(t, ONE_PAGE)
        r = httpx.post(f"{BASE}/documents/{target}/pages/replace", headers=_hdr(t),
                       json={"page": 99, "source_document_id": source, "source_page": 1}, timeout=TIMEOUT)
        assert r.status_code == 400
