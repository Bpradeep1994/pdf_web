"""
Increment 12 tests — Projects / Team Workspaces + Notifications. Run against a live stack.
"""
import time
import httpx
import pytest

BASE    = "http://localhost:8000/api/v1"
TIMEOUT = 30
pytestmark = pytest.mark.integration


def _register():
    t = httpx.post(f"{BASE}/auth/register",
                   json={"email": f"proj_{time.time_ns()}@x.com", "password": "TestPass123!", "full_name": "P"},
                   timeout=TIMEOUT).json()["access_token"]
    uid = httpx.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {t}"}, timeout=TIMEOUT).json()["id"]
    return t, uid


def _hdr(t): return {"Authorization": f"Bearer {t}"}


class TestProjects:
    def test_create_and_list(self):
        t, _ = _register()
        r = httpx.post(f"{BASE}/projects", headers=_hdr(t), json={"name": "Team A", "description": "x"}, timeout=TIMEOUT)
        assert r.status_code == 201 and r.json()["role"] == "owner"
        lst = httpx.get(f"{BASE}/projects", headers=_hdr(t), timeout=TIMEOUT)
        assert lst.status_code == 200 and any(p["name"] == "Team A" for p in lst.json())

    def test_member_access_and_rbac(self):
        owner_t, _ = _register()
        member_t, member_id = _register()
        pid = httpx.post(f"{BASE}/projects", headers=_hdr(owner_t), json={"name": "Shared"}, timeout=TIMEOUT).json()["id"]
        # non-member cannot see it
        assert httpx.get(f"{BASE}/projects/{pid}", headers=_hdr(member_t), timeout=TIMEOUT).status_code == 404
        # owner adds member (viewer)
        add = httpx.post(f"{BASE}/projects/{pid}/members", headers=_hdr(owner_t),
                         json={"user_id": member_id, "role": "viewer"}, timeout=TIMEOUT)
        assert add.status_code == 201
        # member can now read
        got = httpx.get(f"{BASE}/projects/{pid}", headers=_hdr(member_t), timeout=TIMEOUT)
        assert got.status_code == 200 and got.json()["role"] == "viewer"
        # viewer cannot delete (owner-only)
        assert httpx.delete(f"{BASE}/projects/{pid}", headers=_hdr(member_t), timeout=TIMEOUT).status_code == 403

    def test_requires_auth(self):
        assert httpx.get(f"{BASE}/projects", timeout=TIMEOUT).status_code == 401


class TestNotifications:
    def test_member_add_generates_notification(self):
        owner_t, _ = _register()
        member_t, member_id = _register()
        pid = httpx.post(f"{BASE}/projects", headers=_hdr(owner_t), json={"name": "Notif"}, timeout=TIMEOUT).json()["id"]
        httpx.post(f"{BASE}/projects/{pid}/members", headers=_hdr(owner_t),
                   json={"user_id": member_id, "role": "editor"}, timeout=TIMEOUT)
        # member should have an unread "project.invited" notification
        cnt = httpx.get(f"{BASE}/notifications/unread-count", headers=_hdr(member_t), timeout=TIMEOUT)
        assert cnt.status_code == 200 and cnt.json()["unread"] >= 1
        lst = httpx.get(f"{BASE}/notifications", headers=_hdr(member_t), timeout=TIMEOUT).json()
        assert any(n["kind"] == "project.invited" for n in lst)
        nid = lst[0]["id"]
        assert httpx.post(f"{BASE}/notifications/{nid}/read", headers=_hdr(member_t), timeout=TIMEOUT).status_code == 200

    def test_read_all(self):
        t, _ = _register()
        assert httpx.post(f"{BASE}/notifications/read-all", headers=_hdr(t), timeout=TIMEOUT).status_code == 200

    def test_requires_auth(self):
        assert httpx.get(f"{BASE}/notifications", timeout=TIMEOUT).status_code == 401
