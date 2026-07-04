"""
Increment 25 — Super Admin panel: user-facing support tickets + admin-endpoint
access control. (Admin-only data paths require a promoted user, exercised manually;
here we lock in the user flow + that non-admins are denied.)
"""
import time
import httpx
import pytest

BASE = "http://localhost:8000/api/v1"
TIMEOUT = 30
pytestmark = pytest.mark.integration


def _client():
    tok = httpx.post(f"{BASE}/auth/register",
                     json={"email": f"i25_{time.time_ns()}@x.com", "password": "TestPass123!", "full_name": "I25"},
                     timeout=TIMEOUT).json()["access_token"]
    return httpx.Client(base_url=BASE, headers={"Authorization": f"Bearer {tok}"}, timeout=TIMEOUT)


def test_support_ticket_create_and_list():
    c = _client()
    r = c.post("/support/tickets", json={"subject": "Help", "message": "Conversion failed", "priority": "high"})
    assert r.status_code == 201, r.text
    tickets = c.get("/support/tickets").json()
    assert any(t["subject"] == "Help" and t["status"] == "open" for t in tickets)
    c.close()


@pytest.mark.parametrize("ep", [
    "stats", "users", "documents", "revenue", "subscriptions",
    "invoices", "support-tickets", "analytics", "settings", "audit-logs",
])
def test_admin_endpoints_require_admin(ep):
    c = _client()   # ordinary (non-admin) user
    assert c.get(f"/admin/{ep}").status_code == 403
    c.close()
