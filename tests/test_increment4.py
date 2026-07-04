"""
Increment 4 tests — E-Signature (self-sign + multi-field signature requests),
built on the canonical signature_requests / signature_fields schema.
Run against a live stack:  pytest tests/test_increment4.py -v
"""
import time
import httpx
import pytest

BASE    = "http://localhost:8000/api/v1"
TIMEOUT = 30
pytestmark = pytest.mark.integration

# 1x1 transparent PNG (data URL form accepted too)
PNG_B64 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
           "YAAAAAYAAjCB0C8AAAAASUVORK5CYII=")

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
    r = httpx.post(f"{BASE}/auth/register",
                   json={"email": f"esign_{time.time_ns()}@x.com", "password": "TestPass123!", "full_name": "E"},
                   timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["access_token"]


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def ctx():
    token = _register()
    up = httpx.post(f"{BASE}/documents", headers=_hdr(token),
                    files={"file": ("doc.pdf", MINIMAL_PDF, "application/pdf")}, timeout=TIMEOUT)
    up.raise_for_status()
    return {"token": token, "doc_id": up.json()["id"]}


class TestRegistrationStillWorks:
    """Guards the create_user_quota trigger / canonical schema (regression)."""
    def test_register_and_me(self):
        t = _register()
        r = httpx.get(f"{BASE}/auth/me", headers=_hdr(t), timeout=TIMEOUT)
        assert r.status_code == 200


class TestSelfSign:
    def test_apply_signature(self, ctx):
        r = httpx.post(f"{BASE}/signatures/apply", headers=_hdr(ctx["token"]),
                       json={"document_id": ctx["doc_id"], "signature_base64": PNG_B64,
                             "page": 1, "x": 100, "y": 100, "width": 120, "height": 40}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        assert r.json()["document_id"] == ctx["doc_id"]

    def test_invalid_base64_rejected(self, ctx):
        r = httpx.post(f"{BASE}/signatures/apply", headers=_hdr(ctx["token"]),
                       json={"document_id": ctx["doc_id"], "signature_base64": "%%%notbase64%%%",
                             "x": 10, "y": 10}, timeout=TIMEOUT)
        assert r.status_code == 400

    def test_other_user_cannot_sign_my_doc(self, ctx):
        other = _register()
        r = httpx.post(f"{BASE}/signatures/apply", headers=_hdr(other),
                       json={"document_id": ctx["doc_id"], "signature_base64": PNG_B64,
                             "x": 10, "y": 10}, timeout=TIMEOUT)
        assert r.status_code == 404


class TestSignatureRequests:
    def test_full_flow(self, ctx):
        req = httpx.post(f"{BASE}/signatures/requests", headers=_hdr(ctx["token"]),
                         json={"document_id": ctx["doc_id"], "title": "Please sign",
                               "fields": [{"signer_email": "a@x.com", "page_number": 1,
                                           "x": 80, "y": 700, "width": 160, "height": 50}]},
                         timeout=TIMEOUT)
        assert req.status_code == 201, req.text
        body = req.json()
        assert body["status"] == "pending" and len(body["fields"]) == 1
        req_id   = body["id"]
        field_id = body["fields"][0]["id"]

        signed = httpx.post(f"{BASE}/signatures/requests/{req_id}/sign", headers=_hdr(ctx["token"]),
                            json={"field_id": field_id, "signature_base64": PNG_B64}, timeout=TIMEOUT)
        assert signed.status_code == 200, signed.text
        out = signed.json()
        assert out["status"] == "completed"
        assert out["fields"][0]["signed"] is True
        assert out["fields"][0]["signed_at"] is not None

    def test_request_needs_fields(self, ctx):
        r = httpx.post(f"{BASE}/signatures/requests", headers=_hdr(ctx["token"]),
                       json={"document_id": ctx["doc_id"], "title": "x", "fields": []}, timeout=TIMEOUT)
        assert r.status_code == 400

    def test_requests_require_auth(self):
        assert httpx.get(f"{BASE}/signatures/requests", timeout=TIMEOUT).status_code == 401
