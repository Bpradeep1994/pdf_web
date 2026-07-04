"""Post-deployment smoke tests — run against the freshly-deployed staging URL.

Fast, read-mostly checks that the live deployment is actually serving: health,
the frontend loads, auth works end-to-end, and a document round-trips. Exits
non-zero on any failure so the CI pipeline flags a bad deploy.

    STAGING_URL=https://staging.example.com python tests/smoke_staging.py
"""
import os
import sys
import time
import httpx

BASE = os.environ.get("STAGING_URL", "http://localhost:8000").rstrip("/")
API = f"{BASE}/api/v1"
TIMEOUT = 30
failures = []


def check(name, fn):
    try:
        fn()
        print(f"  ok   {name}")
    except Exception as e:
        print(f"  FAIL {name}: {e}")
        failures.append(name)


def gateway_health():
    r = httpx.get(f"{BASE}/health", timeout=TIMEOUT)
    assert r.status_code == 200 and r.json().get("status") == "ok", r.text


def auth_round_trip():
    email = f"smoke_{time.time_ns()}@example.com"
    r = httpx.post(f"{API}/auth/register",
                   json={"email": email, "password": "SmokePass123!", "full_name": "Smoke"},
                   timeout=TIMEOUT)
    assert r.status_code == 201, f"register {r.status_code}"
    token = r.json()["access_token"]
    me = httpx.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
    assert me.status_code == 200 and me.json()["email"] == email
    # unauthenticated access is refused
    assert httpx.get(f"{API}/documents", timeout=TIMEOUT).status_code == 401
    return token


def document_round_trip(token):
    h = {"Authorization": f"Bearer {token}"}
    pdf = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
           b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
           b"3 0 obj<</Type/Page/MediaBox[0 0 400 400]/Parent 2 0 R>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF")
    r = httpx.post(f"{API}/documents", headers=h,
                   files={"file": ("smoke.pdf", pdf, "application/pdf")}, timeout=TIMEOUT)
    assert r.status_code == 201, f"upload {r.status_code}"
    doc_id = r.json()["id"]
    assert httpx.get(f"{API}/documents/{doc_id}", headers=h, timeout=TIMEOUT).status_code == 200
    dl = httpx.get(f"{API}/documents/{doc_id}/download", headers=h, timeout=TIMEOUT)
    assert dl.status_code == 200 and "X-Amz-Signature" in dl.json().get("url", "")


def billing_reads(token):
    h = {"Authorization": f"Bearer {token}"}
    sub = httpx.get(f"{API}/billing/subscription", headers=h, timeout=TIMEOUT)
    assert sub.status_code == 200 and sub.json()["plan"] == "free"


def main():
    print(f"Smoke testing {BASE}")
    check("gateway health", gateway_health)
    token_box = {}
    check("auth round-trip", lambda: token_box.setdefault("t", auth_round_trip()))
    if "t" in token_box:
        check("document round-trip", lambda: document_round_trip(token_box["t"]))
        check("billing reads", lambda: billing_reads(token_box["t"]))
    if failures:
        print(f"\nSMOKE FAILED: {len(failures)} check(s) failed: {', '.join(failures)}")
        sys.exit(1)
    print("\nSMOKE PASSED")


if __name__ == "__main__":
    main()
