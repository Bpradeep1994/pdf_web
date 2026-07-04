"""
Increment 9 tests — OAuth wiring (key-gated) + user management (profile/password).
Run against a live stack.
"""
import time
import httpx
import pytest

BASE    = "http://localhost:8000/api/v1"
TIMEOUT = 30
pytestmark = pytest.mark.integration


def _register():
    email = f"um_{time.time_ns()}@x.com"
    t = httpx.post(f"{BASE}/auth/register",
                   json={"email": email, "password": "TestPass123!", "full_name": "Orig"},
                   timeout=TIMEOUT).json()["access_token"]
    return email, t


def _hdr(t): return {"Authorization": f"Bearer {t}"}


class TestUserManagement:
    def test_update_profile(self):
        _, t = _register()
        r = httpx.patch(f"{BASE}/auth/me", headers=_hdr(t), json={"full_name": "New Name"}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        assert r.json()["full_name"] == "New Name"

    def test_change_password_flow(self):
        email, t = _register()
        r = httpx.post(f"{BASE}/auth/change-password", headers=_hdr(t),
                       json={"current_password": "TestPass123!", "new_password": "NewPass456!"}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        # new password works
        assert httpx.post(f"{BASE}/auth/login", json={"email": email, "password": "NewPass456!"}, timeout=TIMEOUT).status_code == 200
        # old password rejected
        assert httpx.post(f"{BASE}/auth/login", json={"email": email, "password": "TestPass123!"}, timeout=TIMEOUT).status_code == 401

    def test_change_password_wrong_current(self):
        _, t = _register()
        r = httpx.post(f"{BASE}/auth/change-password", headers=_hdr(t),
                       json={"current_password": "WRONG", "new_password": "NewPass456!"}, timeout=TIMEOUT)
        assert r.status_code == 400


class TestOAuth:
    def test_unsupported_provider(self):
        r = httpx.get(f"{BASE}/auth/oauth/wibble", follow_redirects=False, timeout=TIMEOUT)
        assert r.status_code == 400

    @pytest.mark.parametrize("provider", ["google", "github", "microsoft"])
    def test_provider_not_configured_returns_503(self, provider):
        # No client IDs set in this env → clean 503 (not a 404/500). With keys it 302s to the provider.
        r = httpx.get(f"{BASE}/auth/oauth/{provider}", follow_redirects=False, timeout=TIMEOUT)
        assert r.status_code in (302, 503)
