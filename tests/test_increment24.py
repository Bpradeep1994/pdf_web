"""
Increment 24 — RBAC permissions, stored annotations, and gateway security headers.
Run on its own or with the full suite (conftest injects the rate-limit bypass).
"""
import time
import httpx
import pytest

BASE = "http://localhost:8000/api/v1"
ROOT = "http://localhost:8000"
TIMEOUT = 30
pytestmark = pytest.mark.integration

MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 300 300]/Parent 2 0 R>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"
)


def _client():
    tok = httpx.post(f"{BASE}/auth/register",
                     json={"email": f"i24_{time.time_ns()}@x.com", "password": "TestPass123!", "full_name": "I24"},
                     timeout=TIMEOUT).json()["access_token"]
    return httpx.Client(base_url=BASE, headers={"Authorization": f"Bearer {tok}"}, timeout=TIMEOUT)


def test_permissions_endpoint():
    c = _client()
    body = c.get("/auth/permissions").json()
    assert "role" in body and isinstance(body["permissions"], list)
    assert "document:read" in body["permissions"]
    c.close()


def test_annotation_crud():
    c = _client()
    doc = c.post("/documents", files={"file": ("a.pdf", MINIMAL_PDF, "application/pdf")}).json()["id"]
    r = c.post(f"/documents/{doc}/annotations",
               json={"page_number": 1, "type": "highlight", "color": "#ff0",
                     "x": 10, "y": 10, "width": 50, "height": 12, "data": {"note": "hi"}})
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    listed = c.get(f"/documents/{doc}/annotations").json()
    assert len(listed) == 1 and listed[0]["data"] == {"note": "hi"}    # JSONB round-trips
    assert c.patch(f"/documents/{doc}/annotations/{aid}", json={"color": "#0f0"}).status_code == 200
    assert c.delete(f"/documents/{doc}/annotations/{aid}").status_code == 204
    assert c.get(f"/documents/{doc}/annotations").json() == []
    c.close()


def test_annotation_tenant_isolation():
    a, b = _client(), _client()
    doc = a.post("/documents", files={"file": ("a.pdf", MINIMAL_PDF, "application/pdf")}).json()["id"]
    a.post(f"/documents/{doc}/annotations", json={"page_number": 1, "type": "note", "data": {}})
    assert b.get(f"/documents/{doc}/annotations").status_code in (403, 404)   # not yours
    a.close(); b.close()


def test_security_headers():
    h = httpx.get(f"{ROOT}/health", timeout=TIMEOUT).headers
    assert h.get("x-content-type-options") == "nosniff"
    assert h.get("x-frame-options") == "DENY"
    assert "content-security-policy" in h
