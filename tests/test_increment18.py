"""Increment 18 — vector shapes (arrow, triangle, polygon)."""
import time, httpx, pytest
BASE = "http://localhost:8000/api/v1"; TIMEOUT = 30
pytestmark = pytest.mark.integration
PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
       b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
       b"3 0 obj<</Type/Page/MediaBox[0 0 400 400]/Parent 2 0 R>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF")


def _ctx():
    t = httpx.post(f"{BASE}/auth/register", json={"email": f"sh_{time.time_ns()}@x.com", "password": "TestPass123!", "full_name": "S"}, timeout=TIMEOUT).json()["access_token"]
    h = {"Authorization": f"Bearer {t}"}
    d = httpx.post(f"{BASE}/documents", headers=h, files={"file": ("d.pdf", PDF, "application/pdf")}, timeout=TIMEOUT).json()["id"]
    return h, d


def test_arrow():
    h, d = _ctx()
    r = httpx.post(f"{BASE}/documents/{d}/edit/shape", headers=h,
                   json={"page": 1, "shape": "arrow", "x0": 50, "y0": 50, "x1": 200, "y1": 200}, timeout=TIMEOUT)
    assert r.status_code == 200, r.text


def test_triangle():
    h, d = _ctx()
    r = httpx.post(f"{BASE}/documents/{d}/edit/shape", headers=h,
                   json={"page": 1, "shape": "triangle", "x0": 50, "y0": 50, "x1": 200, "y1": 200,
                         "fill": [0.9, 0.9, 0.2]}, timeout=TIMEOUT)
    assert r.status_code == 200, r.text


def test_polygon():
    h, d = _ctx()
    r = httpx.post(f"{BASE}/documents/{d}/edit/shape", headers=h,
                   json={"page": 1, "shape": "polygon", "points": [[100, 100], [200, 120], [180, 220], [90, 200]]}, timeout=TIMEOUT)
    assert r.status_code == 200, r.text


def test_polygon_too_few_points():
    h, d = _ctx()
    r = httpx.post(f"{BASE}/documents/{d}/edit/shape", headers=h,
                   json={"page": 1, "shape": "polygon", "points": [[1, 1], [2, 2]]}, timeout=TIMEOUT)
    assert r.status_code == 400
