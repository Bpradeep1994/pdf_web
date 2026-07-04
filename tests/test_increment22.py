"""
Increment 22 — coverage for the routes wired into the new UI:
comments, signatures (self-sign + multi-signer request flow), watermark, page tools,
folders, projects, notifications, API keys, document rename/move, version restore.

Run against a live stack, on its own (the per-IP rate limiter trips if run with other suites):
    python -m pytest tests/test_increment22.py -q
"""
import base64
import struct
import time
import zlib

import httpx
import pytest

BASE = "http://localhost:8000/api/v1"
TIMEOUT = 30
pytestmark = pytest.mark.integration

MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 300 300]/Parent 2 0 R>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"
)


def _png(w: int = 8, h: int = 8) -> str:
    def chunk(t: bytes, d: bytes) -> bytes:
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\x00\x00\x00" * w for _ in range(h))
    data = (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    return base64.b64encode(data).decode()


def _client():
    """Register a fresh user → authenticated httpx client + token."""
    email = f"i22_{time.time_ns()}@x.com"
    tok = httpx.post(f"{BASE}/auth/register",
                     json={"email": email, "password": "TestPass123!", "full_name": "I22"},
                     timeout=TIMEOUT).json()["access_token"]
    return httpx.Client(base_url=BASE, headers={"Authorization": f"Bearer {tok}"}, timeout=TIMEOUT), tok


def _doc(c: httpx.Client) -> str:
    return c.post("/documents", files={"file": ("d.pdf", MINIMAL_PDF, "application/pdf")}).json()["id"]


@pytest.fixture(scope="module")
def session():
    c, _ = _client()
    yield c
    c.close()


# ── Comments ────────────────────────────────────────────────────────────────
class TestComments:
    def test_crud(self, session):
        doc = _doc(session)
        r = session.post(f"/documents/{doc}/comments", json={"content": "Looks good", "page": 1})
        assert r.status_code == 201, r.text
        cid = r.json()["id"]
        assert any(x["id"] == cid for x in session.get(f"/documents/{doc}/comments").json())
        assert session.patch(f"/documents/{doc}/comments/{cid}", json={"resolved": True}).status_code == 200
        assert session.delete(f"/documents/{doc}/comments/{cid}").status_code == 204
        assert all(x["id"] != cid for x in session.get(f"/documents/{doc}/comments").json())


# ── Signatures ──────────────────────────────────────────────────────────────
class TestSignatures:
    def test_self_sign(self, session):
        doc = _doc(session)
        r = session.post("/signatures/apply", json={
            "document_id": doc, "signature_base64": _png(), "page": 1,
            "x": 72, "y": 72, "width": 150, "height": 60})
        assert r.status_code == 200, r.text

    def test_request_and_complete(self, session):
        doc = _doc(session)
        req = session.post("/signatures/requests", json={
            "document_id": doc, "title": "NDA",
            "fields": [{"signer_email": "a@x.com", "page_number": 1, "x": 72, "y": 72,
                        "width": 150, "height": 60, "field_type": "signature"}]}).json()
        assert req["status"] == "pending"
        fid = req["fields"][0]["id"]
        done = session.post(f"/signatures/requests/{req['id']}/sign",
                            json={"field_id": fid, "signature_base64": _png()})
        assert done.status_code == 200, done.text
        assert done.json()["status"] == "completed"
        # cannot sign an already-completed request again
        assert session.post(f"/signatures/requests/{req['id']}/sign",
                            json={"field_id": fid, "signature_base64": _png()}).status_code == 400

    def test_empty_request_rejected(self, session):
        doc = _doc(session)
        assert session.post("/signatures/requests",
                            json={"document_id": doc, "fields": []}).status_code == 400


# ── Watermark + page tools + versions ──────────────────────────────────────
class TestPageToolsAndWatermark:
    def test_watermark_creates_version(self, session):
        doc = _doc(session)
        assert session.post(f"/documents/{doc}/edit/watermark", json={"text": "CONFIDENTIAL"}).status_code == 200
        assert len(session.get(f"/documents/{doc}/versions").json()) >= 1

    def test_merge(self, session):
        a = session.post("/documents", files={"file": ("a.pdf", MINIMAL_PDF, "application/pdf")}).json()["id"]
        b = session.post("/documents", files={"file": ("b.pdf", MINIMAL_PDF, "application/pdf")}).json()["id"]
        r = session.post("/documents/merge", json={"document_ids": [a, b]})
        assert r.status_code == 201, r.text
        assert r.json().get("page_count") == 2
        assert session.get(f"/documents/{r.json()['id']}/download").status_code == 200

    def test_page_tools(self, session):
        doc = _doc(session)
        assert session.post(f"/documents/{doc}/pages/duplicate", json={"pages": [1]}).status_code == 200
        assert session.post(f"/documents/{doc}/pages/rotate", json={"pages": [1], "degrees": 90}).status_code == 200
        ext = session.post(f"/documents/{doc}/pages/extract", json={"pages": [1]})
        assert ext.status_code == 201 and ext.json().get("id")   # extract → new document
        assert session.post(f"/documents/{doc}/pages/delete", json={"pages": [2]}).status_code == 200

    def test_version_restore(self, session):
        doc = _doc(session)
        session.post(f"/documents/{doc}/edit/watermark", json={"text": "V2"})
        versions = session.get(f"/documents/{doc}/versions").json()
        assert versions, "expected at least one version"
        v = versions[0]["version"]
        assert session.post(f"/documents/{doc}/versions/{v}/restore").status_code in (200, 201)

    def test_table_extraction(self, session):
        doc = _doc(session)
        r = session.get(f"/documents/{doc}/tables", params={"page": 1})
        assert r.status_code == 200 and "count" in r.json()


# ── Folders + rename/move ───────────────────────────────────────────────────
class TestFoldersAndMove:
    def test_folder_and_move(self, session):
        doc = _doc(session)
        f = session.post("/folders", json={"name": "Contracts"})
        assert f.status_code in (200, 201), f.text
        fid = f.json()["id"]
        assert any(x["id"] == fid for x in session.get("/folders").json())
        assert session.patch(f"/documents/{doc}", json={"folder_id": fid}).status_code == 200
        assert session.patch(f"/documents/{doc}", json={"original_name": "renamed.pdf"}).status_code == 200


# ── Projects ────────────────────────────────────────────────────────────────
class TestProjects:
    def test_crud(self, session):
        p = session.post("/projects", json={"name": "Q3 Launch", "description": "docs"})
        assert p.status_code in (200, 201), p.text
        pid = p.json()["id"]
        assert any(x["id"] == pid for x in session.get("/projects").json())
        assert session.delete(f"/projects/{pid}").status_code in (200, 204)


# ── Notifications ───────────────────────────────────────────────────────────
class TestNotifications:
    def test_list_and_count(self, session):
        assert session.get("/notifications").status_code == 200
        assert "unread" in session.get("/notifications/unread-count").json()
        assert session.post("/notifications/read-all").status_code in (200, 204)


# ── API keys ────────────────────────────────────────────────────────────────
class TestApiKeys:
    def test_create_list_revoke(self, session):
        k = session.post("/keys", json={"name": "CI"})
        assert k.status_code in (200, 201), k.text
        assert k.json()["key"].startswith("pk_")   # raw key shown exactly once, no id
        listed = session.get("/keys").json()
        kid = next(x["id"] for x in listed if x["name"] == "CI")
        assert session.delete(f"/keys/{kid}").status_code in (200, 204)
