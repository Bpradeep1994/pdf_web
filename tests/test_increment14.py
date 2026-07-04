"""
Increment 14 (PDFForge gap-fill) — Folders + rename/move, page tools, comments+mentions.
Run against a live stack.
"""
import time
import httpx
import pytest

BASE    = "http://localhost:8000/api/v1"
TIMEOUT = 30
pytestmark = pytest.mark.integration

# 3-page PDF
THREE_PAGE_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R 4 0 R 5 0 R]/Count 3>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 200 200]/Parent 2 0 R>>endobj\n"
    b"4 0 obj<</Type/Page/MediaBox[0 0 200 200]/Parent 2 0 R>>endobj\n"
    b"5 0 obj<</Type/Page/MediaBox[0 0 200 200]/Parent 2 0 R>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF"
)


def _reg():
    return httpx.post(f"{BASE}/auth/register",
                      json={"email": f"pf_{time.time_ns()}@x.com", "password": "TestPass123!", "full_name": "PF"},
                      timeout=TIMEOUT).json()["access_token"]


def _hdr(t): return {"Authorization": f"Bearer {t}"}


def _doc(t):
    return httpx.post(f"{BASE}/documents", headers=_hdr(t),
                      files={"file": ("d.pdf", THREE_PAGE_PDF, "application/pdf")}, timeout=TIMEOUT).json()["id"]


class TestFolders:
    def test_folder_crud_and_move(self):
        t = _reg(); d = _doc(t)
        f = httpx.post(f"{BASE}/folders", headers=_hdr(t), json={"name": "Invoices"}, timeout=TIMEOUT)
        assert f.status_code == 201
        fid = f.json()["id"]
        assert any(x["name"] == "Invoices" for x in httpx.get(f"{BASE}/folders", headers=_hdr(t), timeout=TIMEOUT).json())
        # move document into folder
        mv = httpx.patch(f"{BASE}/documents/{d}", headers=_hdr(t), json={"folder_id": fid}, timeout=TIMEOUT)
        assert mv.status_code == 200
        docs = httpx.get(f"{BASE}/folders/{fid}/documents", headers=_hdr(t), timeout=TIMEOUT).json()
        assert any(x["id"] == d for x in docs)
        # rename folder
        assert httpx.patch(f"{BASE}/folders/{fid}", headers=_hdr(t), json={"name": "Bills"}, timeout=TIMEOUT).status_code == 200

    def test_rename_document(self):
        t = _reg(); d = _doc(t)
        r = httpx.patch(f"{BASE}/documents/{d}", headers=_hdr(t), json={"original_name": "Renamed.pdf"}, timeout=TIMEOUT)
        assert r.status_code == 200 and r.json()["original_name"] == "Renamed.pdf"

    def test_folder_requires_auth(self):
        assert httpx.get(f"{BASE}/folders", timeout=TIMEOUT).status_code == 401


class TestPageTools:
    def test_rotate_delete_reorder_extract(self):
        t = _reg(); d = _doc(t)
        assert httpx.post(f"{BASE}/documents/{d}/pages/rotate", headers=_hdr(t),
                          json={"pages": [1], "degrees": 90}, timeout=TIMEOUT).status_code == 200
        assert httpx.post(f"{BASE}/documents/{d}/pages/reorder", headers=_hdr(t),
                          json={"order": [3, 2, 1]}, timeout=TIMEOUT).status_code == 200
        ext = httpx.post(f"{BASE}/documents/{d}/pages/extract", headers=_hdr(t),
                         json={"pages": [1, 2]}, timeout=TIMEOUT)
        assert ext.status_code == 201 and ext.json()["page_count"] == 2
        assert httpx.post(f"{BASE}/documents/{d}/pages/delete", headers=_hdr(t),
                          json={"pages": [1]}, timeout=TIMEOUT).status_code == 200

    def test_reorder_bad_permutation(self):
        t = _reg(); d = _doc(t)
        assert httpx.post(f"{BASE}/documents/{d}/pages/reorder", headers=_hdr(t),
                          json={"order": [1, 1, 1]}, timeout=TIMEOUT).status_code == 400


class TestComments:
    def test_comment_thread_and_resolve(self):
        t = _reg(); d = _doc(t)
        c = httpx.post(f"{BASE}/documents/{d}/comments", headers=_hdr(t),
                       json={"content": "Please review", "page": 1, "x": 10, "y": 20}, timeout=TIMEOUT)
        assert c.status_code == 201
        cid = c.json()["id"]
        lst = httpx.get(f"{BASE}/documents/{d}/comments", headers=_hdr(t), timeout=TIMEOUT).json()
        assert len(lst) == 1
        assert httpx.patch(f"{BASE}/documents/{d}/comments/{cid}", headers=_hdr(t),
                           json={"resolved": True}, timeout=TIMEOUT).status_code == 200
        assert httpx.delete(f"{BASE}/documents/{d}/comments/{cid}", headers=_hdr(t), timeout=TIMEOUT).status_code == 204

    def test_mention_notifies_user(self):
        owner = _reg(); d = _doc(owner)
        other = _reg()
        other_id = httpx.get(f"{BASE}/auth/me", headers=_hdr(other), timeout=TIMEOUT).json()["id"]
        httpx.post(f"{BASE}/documents/{d}/comments", headers=_hdr(owner),
                   json={"content": "hey @you", "mentions": [other_id]}, timeout=TIMEOUT)
        cnt = httpx.get(f"{BASE}/notifications/unread-count", headers=_hdr(other), timeout=TIMEOUT).json()
        assert cnt["unread"] >= 1
