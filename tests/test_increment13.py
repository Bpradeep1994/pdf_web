"""
Increment 13 tests — Enterprise API keys + editor shapes/image. Run against a live stack.
"""
import time
import httpx
import pytest

BASE    = "http://localhost:8000/api/v1"
TIMEOUT = 30
pytestmark = pytest.mark.integration

PNG_B64 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
           "YAAAAAYAAjCB0C8AAAAASUVORK5CYII=")
MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n"
    b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF"
)


def _register():
    return httpx.post(f"{BASE}/auth/register",
                      json={"email": f"k_{time.time_ns()}@x.com", "password": "TestPass123!", "full_name": "K"},
                      timeout=TIMEOUT).json()["access_token"]


def _hdr(t): return {"Authorization": f"Bearer {t}"}


class TestApiKeys:
    def test_create_use_revoke(self):
        t = _register()
        # create key (raw shown once)
        c = httpx.post(f"{BASE}/keys", headers=_hdr(t), json={"name": "ci"}, timeout=TIMEOUT)
        assert c.status_code == 201
        raw = c.json()["key"]
        assert raw.startswith("pk_")
        # list shows it without the raw secret
        lst = httpx.get(f"{BASE}/keys", headers=_hdr(t), timeout=TIMEOUT).json()
        assert len(lst) == 1 and "key" not in lst[0]
        kid = lst[0]["id"]
        # use the key (no Bearer) on a protected endpoint
        r = httpx.get(f"{BASE}/documents", headers={"X-API-Key": raw}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        # revoke → key no longer works
        assert httpx.delete(f"{BASE}/keys/{kid}", headers=_hdr(t), timeout=TIMEOUT).status_code == 204
        assert httpx.get(f"{BASE}/documents", headers={"X-API-Key": raw}, timeout=TIMEOUT).status_code == 401

    def test_bad_key_rejected(self):
        r = httpx.get(f"{BASE}/documents", headers={"X-API-Key": "pk_invalid"}, timeout=TIMEOUT)
        assert r.status_code == 401

    def test_keys_require_auth(self):
        assert httpx.get(f"{BASE}/keys", timeout=TIMEOUT).status_code == 401


class TestEditorShapesImage:
    def _doc(self, t):
        return httpx.post(f"{BASE}/documents", headers=_hdr(t),
                          files={"file": ("d.pdf", MINIMAL_PDF, "application/pdf")}, timeout=TIMEOUT).json()["id"]

    def test_add_shape(self):
        t = _register(); d = self._doc(t)
        r = httpx.post(f"{BASE}/documents/{d}/edit/shape", headers=_hdr(t),
                       json={"page": 1, "shape": "rect", "x0": 50, "y0": 50, "x1": 200, "y1": 150}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text

    def test_bad_shape_rejected(self):
        # NB: triangle/polygon/arrow are now supported; use a genuinely invalid shape.
        t = _register(); d = self._doc(t)
        r = httpx.post(f"{BASE}/documents/{d}/edit/shape", headers=_hdr(t),
                       json={"page": 1, "shape": "blob", "x0": 0, "y0": 0, "x1": 1, "y1": 1}, timeout=TIMEOUT)
        assert r.status_code == 400

    def test_add_image(self):
        t = _register(); d = self._doc(t)
        r = httpx.post(f"{BASE}/documents/{d}/edit/image", headers=_hdr(t),
                       json={"page": 1, "image_base64": PNG_B64, "x": 100, "y": 100, "width": 80, "height": 40},
                       timeout=TIMEOUT)
        assert r.status_code == 200, r.text
