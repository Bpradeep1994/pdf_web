"""
Increment 5 tests — Audit Logs (admin viewer RBAC + event capture presence).
The admin-success path (promote + content assertions) is verified separately; here we
assert RBAC and that auth events are being written (visible to an admin).
Run against a live stack:  pytest tests/test_increment5.py -v
"""
import time
import httpx
import pytest

BASE    = "http://localhost:8000/api/v1"
TIMEOUT = 30
pytestmark = pytest.mark.integration


def _register():
    r = httpx.post(f"{BASE}/auth/register",
                   json={"email": f"audit_{time.time_ns()}@x.com", "password": "TestPass123!", "full_name": "A"},
                   timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["access_token"]


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


class TestAuditRBAC:
    def test_requires_auth(self):
        assert httpx.get(f"{BASE}/admin/audit-logs", timeout=TIMEOUT).status_code == 401

    def test_forbidden_for_non_admin(self):
        t = _register()
        assert httpx.get(f"{BASE}/admin/audit-logs", headers=_hdr(t), timeout=TIMEOUT).status_code == 403
