"""
Increment 11 tests — Billing (Stripe), key-gated. With no Stripe keys: read endpoints
work; action endpoints return a clean 503. Run against a live stack.
"""
import time
import httpx
import pytest

BASE    = "http://localhost:8000/api/v1"
TIMEOUT = 30
pytestmark = pytest.mark.integration


def _register():
    return httpx.post(f"{BASE}/auth/register",
                      json={"email": f"bill_{time.time_ns()}@x.com", "password": "TestPass123!", "full_name": "B"},
                      timeout=TIMEOUT).json()["access_token"]


def _hdr(t): return {"Authorization": f"Bearer {t}"}


class TestBillingReads:
    def test_plans(self):
        r = httpx.get(f"{BASE}/billing/plans", headers=_hdr(_register()), timeout=TIMEOUT)
        assert r.status_code == 200
        body = r.json()
        assert "enabled" in body
        ids = {p["id"] for p in body["plans"]}
        assert {"free", "pro", "business", "enterprise"}.issubset(ids)

    def test_subscription_seeded_free(self):
        # the create_user_quota trigger seeds a 'free' subscription on registration
        r = httpx.get(f"{BASE}/billing/subscription", headers=_hdr(_register()), timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json()["plan"] == "free"

    def test_invoices_empty(self):
        r = httpx.get(f"{BASE}/billing/invoices", headers=_hdr(_register()), timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json() == []

    def test_requires_auth(self):
        assert httpx.get(f"{BASE}/billing/subscription", timeout=TIMEOUT).status_code == 401


class TestBillingActions:
    # Mode-aware: 503 when Stripe keys are absent; 400 when enabled-but-no-price-IDs
    # (checkout) or bad-signature (webhook). Never 200/500 in either mode here, and
    # we avoid making real successful Stripe calls from tests.
    def test_checkout_no_price_id_or_disabled(self):
        r = httpx.post(f"{BASE}/billing/checkout", headers=_hdr(_register()),
                       json={"plan": "pro"}, timeout=TIMEOUT)
        if r.status_code == 200:
            # Dev/demo mode (no Stripe keys): mock checkout URL, flagged dev=true
            body = r.json()
            assert body.get("dev") is True and "checkout_url" in body, r.text
        else:
            assert r.status_code in (400, 503), r.text

    def test_checkout_requires_auth(self):
        assert httpx.post(f"{BASE}/billing/checkout", json={"plan": "pro"}, timeout=TIMEOUT).status_code == 401

    def test_portal_requires_auth(self):
        assert httpx.post(f"{BASE}/billing/portal", timeout=TIMEOUT).status_code == 401

    def test_webhook_public_rejects_bad_signature(self):
        # public (no auth → not 401); 400 bad-signature when enabled, 503 when disabled
        r = httpx.post(f"{BASE}/billing/webhook", content=b"{}", timeout=TIMEOUT)
        assert r.status_code in (400, 503)
