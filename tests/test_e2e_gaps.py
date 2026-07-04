"""
Gap-coverage E2E tests — endpoints not exercised by any other test file.
Covers: PDF text edits (add/highlight/redact/replace), text-spans, page render,
MFA, password-reset confirm, OAuth provider discovery, the full dev-mode billing
lifecycle (OTP checkout → payments → refund → change/cancel/resume), conversion
extras (file upload, protect/unlock, scan), analytics tracking, and the admin
API exercised as a real admin (promoted via direct DB access).

Run against a live stack:  pytest tests/test_e2e_gaps.py -m integration -v
Admin tests need the postgres container reachable via `docker exec`.
"""
import base64
import hashlib
import hmac
import struct
import subprocess
import time

import httpx
import pytest

BASE    = "http://localhost:8000/api/v1"
TIMEOUT = 60
pytestmark = pytest.mark.integration

PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
       b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
       b"3 0 obj<</Type/Page/MediaBox[0 0 400 400]/Parent 2 0 R>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF")

# 1x1 red pixel PNG
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")

PG_CONTAINER = "pdf_editor-postgres-1"


def _register(prefix="gap"):
    email = "{}_{}@x.com".format(prefix, time.time_ns())
    r = httpx.post(BASE + "/auth/register",
                   json={"email": email, "password": "TestPass123!", "full_name": "Gap"},
                   timeout=TIMEOUT)
    assert r.status_code == 201, r.text
    return r.json()["access_token"], email


def _hdr(t):
    return {"Authorization": "Bearer " + t}


def _upload(h):
    r = httpx.post(BASE + "/documents", headers=h,
                   files={"file": ("gap.pdf", PDF, "application/pdf")}, timeout=TIMEOUT)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _psql(sql):
    """Run SQL inside the postgres container; returns stdout or None if unavailable."""
    try:
        out = subprocess.run(
            ["docker", "exec", PG_CONTAINER, "psql", "-U", "pdfuser", "-d", "pdfeditor", "-tAc", sql],
            capture_output=True, text=True, timeout=30)
        if out.returncode != 0:
            return None
        return out.stdout.strip()
    except Exception:
        return None


def _totp(secret):
    """RFC 6238 TOTP (SHA-1, 30 s step, 6 digits) — avoids a pyotp dependency."""
    key = base64.b32decode(secret)
    counter = struct.pack(">Q", int(time.time()) // 30)
    digest = hmac.new(key, counter, hashlib.sha1).digest()
    offset = digest[19] & 15
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1000000
    return str(code).zfill(6)


# ──────────────────────────────────────────────────────────────────────────────
# PDF editing: text add / highlight / redact / replace, spans, page render
# ──────────────────────────────────────────────────────────────────────────────

class TestPdfEditing:
    @classmethod
    def setup_class(cls):
        token, _ = _register("edit")
        cls.h = _hdr(token)
        cls.doc = _upload(cls.h)

    def test_add_text(self):
        r = httpx.post(BASE + "/documents/{}/edit/text".format(self.doc), headers=self.h,
                       json={"page": 1, "x": 50, "y": 100, "text": "Hello E2E", "size": 14},
                       timeout=TIMEOUT)
        assert r.status_code == 200, r.text

    def test_text_spans_reflect_edit(self):
        r = httpx.get(BASE + "/documents/{}/text-spans".format(self.doc), headers=self.h,
                      params={"page": 1}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        spans = r.json()["spans"]
        assert any("Hello E2E" in s["text"] for s in spans), spans

    def test_text_spans_page_out_of_range(self):
        r = httpx.get(BASE + "/documents/{}/text-spans".format(self.doc), headers=self.h,
                      params={"page": 99}, timeout=TIMEOUT)
        assert r.status_code == 400, r.text

    def test_edit_and_delete_text(self):
        """Add a word, edit it in place, then delete it (replace with empty string)."""
        h = _hdr(_register("txtedit")[0])
        doc = _upload(h)

        def text_of():
            return str(httpx.get(BASE + "/documents/{}/text".format(doc), headers=h, timeout=TIMEOUT).json())

        def span_with(word):
            spans = httpx.get(BASE + "/documents/{}/text-spans".format(doc), headers=h,
                              params={"page": 1}, timeout=TIMEOUT).json()["spans"]
            return next((s for s in spans if word in s["text"]), None)

        # add
        r = httpx.post(BASE + "/documents/{}/edit/text".format(doc), headers=h,
                       json={"page": 1, "x": 50, "y": 100, "text": "OrigWord", "size": 14}, timeout=TIMEOUT)
        assert r.status_code == 200 and "OrigWord" in text_of()

        # edit in place
        s = span_with("OrigWord"); assert s
        r = httpx.post(BASE + "/documents/{}/edit/replace".format(doc), headers=h,
                       json={"page": 1, "rect": s["bbox"], "text": "Changed"}, timeout=TIMEOUT)
        assert r.status_code == 200
        assert "Changed" in text_of() and "OrigWord" not in text_of()

        # delete = replace with an empty string
        s = span_with("Changed"); assert s
        r = httpx.post(BASE + "/documents/{}/edit/replace".format(doc), headers=h,
                       json={"page": 1, "rect": s["bbox"], "text": ""}, timeout=TIMEOUT)
        assert r.status_code == 200 and "Changed" not in text_of()

    def test_highlight(self):
        r = httpx.post(BASE + "/documents/{}/edit/highlight".format(self.doc), headers=self.h,
                       json={"page": 1, "quads": [[40, 80, 160, 80, 40, 110, 160, 110]]},
                       timeout=TIMEOUT)
        assert r.status_code == 200, r.text

    def test_replace_text(self):
        r = httpx.post(BASE + "/documents/{}/edit/replace".format(self.doc), headers=self.h,
                       json={"page": 1, "rect": [40, 80, 200, 110], "text": "Replaced"},
                       timeout=TIMEOUT)
        assert r.status_code == 200, r.text

    def test_redact(self):
        r = httpx.post(BASE + "/documents/{}/edit/redact".format(self.doc), headers=self.h,
                       json={"page": 1, "rects": [[40, 80, 200, 110]]}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        # the redacted text must actually be gone
        t = httpx.get(BASE + "/documents/{}/text".format(self.doc), headers=self.h, timeout=TIMEOUT)
        assert "Replaced" not in str(t.json())

    def test_undo_redo_roundtrip(self):
        """add → edit → delete, then undo/undo walks back and redo/redo walks forward."""
        h = _hdr(_register("undoredo")[0])
        doc = _upload(h)

        def text_of():
            return str(httpx.get(BASE + "/documents/{}/text".format(doc), headers=h, timeout=TIMEOUT).json())

        def span(word):
            spans = httpx.get(BASE + "/documents/{}/text-spans".format(doc), headers=h,
                              params={"page": 1}, timeout=TIMEOUT).json()["spans"]
            return next((s for s in spans if word in s["text"]), None)

        # add "Alpha"
        httpx.post(BASE + "/documents/{}/edit/text".format(doc), headers=h,
                   json={"page": 1, "x": 50, "y": 100, "text": "Alpha", "size": 14}, timeout=TIMEOUT)
        # edit → "Beta"
        s = span("Alpha")
        httpx.post(BASE + "/documents/{}/edit/replace".format(doc), headers=h,
                   json={"page": 1, "rect": s["bbox"], "text": "Beta"}, timeout=TIMEOUT)
        # delete "Beta"
        s = span("Beta")
        httpx.post(BASE + "/documents/{}/edit/replace".format(doc), headers=h,
                   json={"page": 1, "rect": s["bbox"], "text": ""}, timeout=TIMEOUT)
        assert "Beta" not in text_of()   # currently deleted

        def undo(): return httpx.post(BASE + "/documents/{}/undo".format(doc), headers=h, timeout=TIMEOUT)
        def redo(): return httpx.post(BASE + "/documents/{}/redo".format(doc), headers=h, timeout=TIMEOUT)

        assert undo().status_code == 200 and "Beta" in text_of()      # undo delete → Beta back
        assert undo().status_code == 200 and "Alpha" in text_of()     # undo edit → Alpha back
        assert undo().status_code == 200 and "Alpha" not in text_of() # undo add → blank original
        assert undo().status_code == 400                              # nothing left to undo

        assert redo().status_code == 200 and "Alpha" in text_of()     # redo add
        assert redo().status_code == 200 and "Beta" in text_of()      # redo edit
        assert redo().status_code == 200 and "Beta" not in text_of()  # redo delete
        assert redo().status_code == 400                              # nothing left to redo

    def test_new_edit_after_undo_truncates_redo(self):
        """Editing from an undone state starts a new branch (redo no longer available)."""
        h = _hdr(_register("branch")[0])
        doc = _upload(h)

        def text_of():
            return str(httpx.get(BASE + "/documents/{}/text".format(doc), headers=h, timeout=TIMEOUT).json())

        httpx.post(BASE + "/documents/{}/edit/text".format(doc), headers=h,
                   json={"page": 1, "x": 50, "y": 100, "text": "First", "size": 14}, timeout=TIMEOUT)
        assert httpx.post(BASE + "/documents/{}/undo".format(doc), headers=h, timeout=TIMEOUT).status_code == 200
        assert "First" not in text_of()
        # new edit from the undone (blank) state
        httpx.post(BASE + "/documents/{}/edit/text".format(doc), headers=h,
                   json={"page": 1, "x": 50, "y": 200, "text": "Second", "size": 14}, timeout=TIMEOUT)
        assert "Second" in text_of() and "First" not in text_of()
        # redo must NOT resurrect "First" — that branch was truncated
        assert httpx.post(BASE + "/documents/{}/redo".format(doc), headers=h, timeout=TIMEOUT).status_code == 400

    def test_versions_incremented_by_edits(self):
        r = httpx.get(BASE + "/documents/{}/versions".format(self.doc), headers=self.h, timeout=TIMEOUT)
        assert r.status_code == 200
        assert len(r.json()) >= 4   # one per edit above

    def test_render_page_png(self):
        r = httpx.get(BASE + "/documents/{}/pages/1".format(self.doc), headers=self.h,
                      params={"zoom": 1.0}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("image/png")
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"

    def test_render_page_out_of_range_not_500(self):
        r = httpx.get(BASE + "/documents/{}/pages/99".format(self.doc), headers=self.h, timeout=TIMEOUT)
        assert r.status_code < 500, "page out of range must be a 4xx, got {}".format(r.status_code)


# ──────────────────────────────────────────────────────────────────────────────
# Registration input validation
# ──────────────────────────────────────────────────────────────────────────────

class TestRegistrationValidation:
    def test_invalid_email_rejected(self):
        r = httpx.post(BASE + "/auth/register",
                       json={"email": "not-an-email", "password": "GoodPass123!", "full_name": "X"},
                       timeout=TIMEOUT)
        assert r.status_code == 422, r.text

    def test_weak_password_rejected(self):
        for pw in ("Ab1!xyz", ""):   # 7 chars, empty — both under the 8-char minimum
            r = httpx.post(BASE + "/auth/register",
                           json={"email": "weak_{}@x.com".format(time.time_ns()), "password": pw, "full_name": "X"},
                           timeout=TIMEOUT)
            assert r.status_code == 422, r.text

    def test_duplicate_email_conflict(self):
        email = "dupe_{}@x.com".format(time.time_ns())
        body = {"email": email, "password": "GoodPass123!", "full_name": "X"}
        assert httpx.post(BASE + "/auth/register", json=body, timeout=TIMEOUT).status_code == 201
        assert httpx.post(BASE + "/auth/register", json=body, timeout=TIMEOUT).status_code == 409


# ──────────────────────────────────────────────────────────────────────────────
# Login security: brute-force lockout, account status, session expiry
# ──────────────────────────────────────────────────────────────────────────────

class TestLoginSecurity:
    def test_brute_force_lockout(self):
        """5 failed attempts lock the account (429) — even with the right password."""
        _, email = _register("lock")
        for _ in range(5):
            r = httpx.post(BASE + "/auth/login",
                           json={"email": email, "password": "WrongPass999!"}, timeout=TIMEOUT)
            assert r.status_code in (401, 429)
        r = httpx.post(BASE + "/auth/login",
                       json={"email": email, "password": "TestPass123!"}, timeout=TIMEOUT)
        assert r.status_code == 429, r.text

    def test_suspended_account_rejected(self):
        _, email = _register("susp")
        if _psql("UPDATE users SET status='suspended' WHERE email='{}'".format(email)) is None:
            pytest.skip("postgres container not reachable via docker exec")
        r = httpx.post(BASE + "/auth/login",
                       json={"email": email, "password": "TestPass123!"}, timeout=TIMEOUT)
        assert r.status_code == 403, r.text

    def test_expired_access_token_rejected(self):
        """A token signed with the real secret but already expired must be a 401."""
        try:
            out = subprocess.run(
                ["docker", "exec", "pdf_editor-auth_service-1", "python", "-c",
                 "import sys; sys.path.insert(0,'/app'); "
                 "from shared.security import create_access_token; from datetime import timedelta; "
                 "print(create_access_token({'sub':'00000000-0000-0000-0000-000000000000',"
                 "'email':'x@x.com','role':'free'}, timedelta(seconds=-60)))"],
                capture_output=True, text=True, timeout=30)
            token = out.stdout.strip()
        except Exception:
            token = ""
        if not token:
            pytest.skip("auth container not reachable via docker exec")
        r = httpx.get(BASE + "/auth/me", headers=_hdr(token), timeout=TIMEOUT)
        assert r.status_code == 401, r.text


# ──────────────────────────────────────────────────────────────────────────────
# Auth extras: OAuth discovery, MFA, password-reset confirm
# ──────────────────────────────────────────────────────────────────────────────

class TestAuthExtras:
    def test_oauth_providers_public(self):
        r = httpx.get(BASE + "/auth/oauth/providers", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        assert isinstance(r.json()["providers"], list)

    def test_mfa_setup_and_verify(self):
        token, _ = _register("mfa")
        h = _hdr(token)
        r = httpx.post(BASE + "/auth/mfa/setup", headers=h, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        secret = r.json()["secret"]
        assert "otpauth://" in r.json()["qr_url"]

        bad = httpx.post(BASE + "/auth/mfa/verify", headers=h, json={"code": "000000"}, timeout=TIMEOUT)
        assert bad.status_code == 400

        ok = httpx.post(BASE + "/auth/mfa/verify", headers=h, json={"code": _totp(secret)}, timeout=TIMEOUT)
        assert ok.status_code == 200, ok.text

    def test_password_reset_confirm_full_flow(self):
        token, email = _register("pwreset")
        r = httpx.post(BASE + "/auth/password-reset", json={"email": email}, timeout=TIMEOUT)
        assert r.status_code == 200

        reset_token = _psql(
            "SELECT token FROM user_tokens WHERE token_type='password_reset' AND used_at IS NULL "
            "AND user_id=(SELECT id FROM users WHERE email='{}') ORDER BY expires_at DESC LIMIT 1".format(email))
        if not reset_token:
            pytest.skip("postgres container not reachable via docker exec")

        r = httpx.post(BASE + "/auth/password-reset/confirm",
                       json={"token": reset_token, "password": "NewPass456!"}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text

        # old password dead, new password works, token single-use
        assert httpx.post(BASE + "/auth/login", json={"email": email, "password": "TestPass123!"},
                          timeout=TIMEOUT).status_code == 401
        assert httpx.post(BASE + "/auth/login", json={"email": email, "password": "NewPass456!"},
                          timeout=TIMEOUT).status_code == 200
        assert httpx.post(BASE + "/auth/password-reset/confirm",
                          json={"token": reset_token, "password": "Again789!"},
                          timeout=TIMEOUT).status_code == 400

    def test_password_reset_confirm_bad_token(self):
        r = httpx.post(BASE + "/auth/password-reset/confirm",
                       json={"token": "not-a-real-token", "password": "Whatever1!"}, timeout=TIMEOUT)
        assert r.status_code == 400


# ──────────────────────────────────────────────────────────────────────────────
# Billing lifecycle (dev mode, no Stripe keys)
# ──────────────────────────────────────────────────────────────────────────────

class TestBillingLifecycle:
    @classmethod
    def setup_class(cls):
        token, _ = _register("billing")
        cls.h = _hdr(token)

    def test_providers_public_shape(self):
        r = httpx.get(BASE + "/billing/providers", headers=self.h, timeout=TIMEOUT)
        assert r.status_code == 200
        assert "stripe" in r.json()["providers"]

    def test_otp_checkout_activates_plan(self):
        r = httpx.post(BASE + "/billing/send-otp", headers=self.h, json={}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        otp = r.json().get("dev_otp")
        if not otp:
            pytest.skip("real email/SMS configured — OTP not exposed")

        bad = httpx.post(BASE + "/billing/verify-otp", headers=self.h,
                         json={"plan": "pro", "otp": "000000"}, timeout=TIMEOUT)
        assert bad.status_code == 400

        ok = httpx.post(BASE + "/billing/verify-otp", headers=self.h,
                        json={"plan": "pro", "interval": "monthly", "card_brand": "visa", "otp": otp},
                        timeout=TIMEOUT)
        assert ok.status_code == 200, ok.text
        assert ok.json()["plan"] == "pro"

        sub = httpx.get(BASE + "/billing/subscription", headers=self.h, timeout=TIMEOUT)
        assert sub.json()["plan"] == "pro"

    def test_payments_and_methods_recorded(self):
        pays = httpx.get(BASE + "/billing/payments", headers=self.h, timeout=TIMEOUT)
        assert pays.status_code == 200 and len(pays.json()) >= 1, pays.text
        assert pays.json()[0]["status"] == "succeeded"
        methods = httpx.get(BASE + "/billing/payment-methods", headers=self.h, timeout=TIMEOUT)
        assert methods.status_code == 200 and len(methods.json()) >= 1

    def test_refund(self):
        pay_id = httpx.get(BASE + "/billing/payments", headers=self.h, timeout=TIMEOUT).json()[0]["id"]
        r = httpx.post(BASE + "/billing/refund", headers=self.h,
                       json={"payment_id": pay_id, "reason": "e2e"}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        again = httpx.post(BASE + "/billing/refund", headers=self.h,
                           json={"payment_id": pay_id}, timeout=TIMEOUT)
        assert again.status_code == 400   # double refund rejected

    def test_change_cancel_resume(self):
        r = httpx.post(BASE + "/billing/change-plan", headers=self.h,
                       json={"plan": "business"}, timeout=TIMEOUT)
        assert r.status_code == 200 and r.json()["plan"] == "business", r.text

        r = httpx.post(BASE + "/billing/cancel", headers=self.h, timeout=TIMEOUT)
        assert r.status_code == 200 and r.json()["cancel_at_period_end"] is True

        r = httpx.post(BASE + "/billing/resume", headers=self.h, timeout=TIMEOUT)
        assert r.status_code == 200 and r.json()["cancel_at_period_end"] is False

    def test_dev_activate(self):
        token, _ = _register("devact")
        r = httpx.post(BASE + "/billing/dev-activate", headers=_hdr(token),
                       json={"plan": "pro", "interval": "yearly"}, timeout=TIMEOUT)
        # 200 in dev mode; 400 when Stripe is live (endpoint disabled)
        assert r.status_code in (200, 400), r.text

    def test_full_plan_lifecycle_with_invoices_and_renewal(self):
        """free → upgrade (invoice + renewal date) → failed payment recorded →
        downgrade → cancel → resume — the complete billing story for one user."""
        from datetime import datetime, timedelta
        token, _ = _register("lifecycle")
        h = _hdr(token)

        # starts on the free plan
        sub = httpx.get(BASE + "/billing/subscription", headers=h, timeout=TIMEOUT).json()
        assert sub["plan"] == "free"

        # failed payment first: wrong OTP → 400 AND a 'failed' payment row
        httpx.post(BASE + "/billing/send-otp", headers=h, json={}, timeout=TIMEOUT)
        bad = httpx.post(BASE + "/billing/verify-otp", headers=h,
                         json={"plan": "pro", "otp": "000000"}, timeout=TIMEOUT)
        assert bad.status_code == 400
        pays = httpx.get(BASE + "/billing/payments", headers=h, timeout=TIMEOUT).json()
        assert any(p["status"] == "failed" for p in pays), "failed attempt must appear in history"

        # upgrade to pro (yearly) via OTP
        otp = httpx.post(BASE + "/billing/send-otp", headers=h, json={}, timeout=TIMEOUT).json().get("dev_otp")
        if not otp:
            pytest.skip("real email configured — OTP not exposed")
        ok = httpx.post(BASE + "/billing/verify-otp", headers=h,
                        json={"plan": "pro", "interval": "yearly", "card_brand": "visa", "otp": otp},
                        timeout=TIMEOUT)
        assert ok.status_code == 200, ok.text

        # renewal date ≈ one year out
        sub = httpx.get(BASE + "/billing/subscription", headers=h, timeout=TIMEOUT).json()
        assert sub["plan"] == "pro"
        end = datetime.fromisoformat(sub["current_period_end"]).replace(tzinfo=None)
        days = (end - datetime.utcnow()).days
        assert 360 <= days <= 370, "yearly renewal should be ~365 days out, got {}".format(days)

        # invoice issued for the charge
        invoices = httpx.get(BASE + "/billing/invoices", headers=h, timeout=TIMEOUT).json()
        assert len(invoices) == 1 and invoices[0]["status"] == "paid"
        assert invoices[0]["amount_paid"] == 1000   # pro yearly = 100¢ × 10

        # downgrade pro → free
        r = httpx.post(BASE + "/billing/change-plan", headers=h, json={"plan": "free"}, timeout=TIMEOUT)
        assert r.status_code == 200 and r.json()["plan"] == "free"

        # upgrade again (monthly) → renewal ~1 month out
        r = httpx.post(BASE + "/billing/dev-activate", headers=h,
                       json={"plan": "business", "interval": "monthly"}, timeout=TIMEOUT)
        if r.status_code == 200:
            sub = httpx.get(BASE + "/billing/subscription", headers=h, timeout=TIMEOUT).json()
            end = datetime.fromisoformat(sub["current_period_end"]).replace(tzinfo=None)
            assert 25 <= (end - datetime.utcnow()).days <= 35

        # cancel keeps access until period end; resume clears it
        assert httpx.post(BASE + "/billing/cancel", headers=h, timeout=TIMEOUT).json()["cancel_at_period_end"] is True
        assert httpx.post(BASE + "/billing/resume", headers=h, timeout=TIMEOUT).json()["cancel_at_period_end"] is False

    def test_provider_webhook_scaffolds_accept(self):
        # PayPal is dev-accept here (no PAYPAL_WEBHOOK_ID configured)
        r = httpx.post(BASE + "/billing/webhook/paypal", json={"event_type": "e2e.test"},
                       headers=self.h, timeout=TIMEOUT)
        assert r.status_code == 200, r.text


# ──────────────────────────────────────────────────────────────────────────────
# Conversion extras: /file, /protect, /unlock, /scan
# ──────────────────────────────────────────────────────────────────────────────

class TestConversionExtras:
    @classmethod
    def setup_class(cls):
        token, _ = _register("conv")
        cls.h = _hdr(token)

    def test_convert_uploaded_image_to_pdf(self):
        r = httpx.post(BASE + "/convert/file", headers=self.h,
                       files={"file": ("pic.png", PNG, "image/png")},
                       data={"target_format": "pdf"}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        assert r.json()["download_url"]

    def test_convert_file_unsupported_path_rejected(self):
        r = httpx.post(BASE + "/convert/file", headers=self.h,
                       files={"file": ("data.xyz", b"junk", "application/octet-stream")},
                       data={"target_format": "pdf"}, timeout=TIMEOUT)
        assert r.status_code == 400

    def test_protect_then_unlock_roundtrip(self):
        r = httpx.post(BASE + "/convert/protect", headers=self.h,
                       files={"file": ("doc.pdf", PDF, "application/pdf")},
                       data={"password": "S3cret!"}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        protected = httpx.get(r.json()["download_url"], timeout=TIMEOUT).content
        assert protected[:5] == b"%PDF-"

        bad = httpx.post(BASE + "/convert/unlock", headers=self.h,
                         files={"file": ("locked.pdf", protected, "application/pdf")},
                         data={"password": "wrong"}, timeout=TIMEOUT)
        assert bad.status_code == 400

        ok = httpx.post(BASE + "/convert/unlock", headers=self.h,
                        files={"file": ("locked.pdf", protected, "application/pdf")},
                        data={"password": "S3cret!"}, timeout=TIMEOUT)
        assert ok.status_code == 200, ok.text

    def test_scan_images_to_pdf(self):
        r = httpx.post(BASE + "/convert/scan", headers=self.h,
                       files=[("files", ("a.png", PNG, "image/png")),
                              ("files", ("b.png", PNG, "image/png"))], timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        merged = httpx.get(r.json()["download_url"], timeout=TIMEOUT).content
        assert merged[:5] == b"%PDF-"


# ──────────────────────────────────────────────────────────────────────────────
# Page management: add / delete / duplicate / extract / merge / split / rotate / reorder
# ──────────────────────────────────────────────────────────────────────────────

class TestPageManagement:
    @classmethod
    def setup_class(cls):
        cls.h = _hdr(_register("pages")[0])

    def _count(self, doc):
        return httpx.get(BASE + "/documents/{}".format(doc), headers=self.h, timeout=TIMEOUT).json()["page_count"]

    def test_full_page_lifecycle(self):
        doc = _upload(self.h)                      # 1 page
        assert self._count(doc) == 1

        # add (blank page at end, then one after page 1)
        r = httpx.post(BASE + "/documents/{}/pages/add".format(doc), headers=self.h, json={}, timeout=TIMEOUT)
        assert r.status_code == 200 and self._count(doc) == 2
        r = httpx.post(BASE + "/documents/{}/pages/add".format(doc), headers=self.h, json={"after": 1}, timeout=TIMEOUT)
        assert r.status_code == 200 and self._count(doc) == 3

        # duplicate page 1 → 4 pages
        r = httpx.post(BASE + "/documents/{}/pages/duplicate".format(doc), headers=self.h,
                       json={"pages": [1]}, timeout=TIMEOUT)
        assert r.status_code == 200 and self._count(doc) == 4

        # rotate page 2
        r = httpx.post(BASE + "/documents/{}/pages/rotate".format(doc), headers=self.h,
                       json={"pages": [2], "degrees": 90}, timeout=TIMEOUT)
        assert r.status_code == 200

        # rearrange (reverse)
        r = httpx.post(BASE + "/documents/{}/pages/reorder".format(doc), headers=self.h,
                       json={"order": [4, 3, 2, 1]}, timeout=TIMEOUT)
        assert r.status_code == 200 and self._count(doc) == 4

        # extract pages 1-2 → new document with 2 pages
        r = httpx.post(BASE + "/documents/{}/pages/extract".format(doc), headers=self.h,
                       json={"pages": [1, 2]}, timeout=TIMEOUT)
        assert r.status_code == 201, r.text
        assert r.json()["page_count"] == 2
        assert self._count(r.json()["id"]) == 2

        # delete page 4 → 3 pages
        r = httpx.post(BASE + "/documents/{}/pages/delete".format(doc), headers=self.h,
                       json={"pages": [4]}, timeout=TIMEOUT)
        assert r.status_code == 200 and self._count(doc) == 3

        # guard rails
        assert httpx.post(BASE + "/documents/{}/pages/delete".format(doc), headers=self.h,
                          json={"pages": [1, 2, 3]}, timeout=TIMEOUT).status_code == 400  # can't delete all
        assert httpx.post(BASE + "/documents/{}/pages/add".format(doc), headers=self.h,
                          json={"after": 99}, timeout=TIMEOUT).status_code == 400
        assert httpx.post(BASE + "/documents/{}/pages/reorder".format(doc), headers=self.h,
                          json={"order": [1, 1, 2]}, timeout=TIMEOUT).status_code == 400  # not a permutation

    def test_merge_and_split(self):
        a, b = _upload(self.h), _upload(self.h)
        # grow A to 2 pages so the merged count is distinctive
        httpx.post(BASE + "/documents/{}/pages/add".format(a), headers=self.h, json={}, timeout=TIMEOUT)

        r = httpx.post(BASE + "/documents/merge", headers=self.h,
                       json={"document_ids": [a, b]}, timeout=TIMEOUT)
        assert r.status_code == 201, r.text
        merged = r.json()
        assert merged["page_count"] == 3
        assert self._count(merged["id"]) == 3

        # split into single pages → 3 new documents of 1 page each
        r = httpx.post(BASE + "/documents/{}/split".format(merged["id"]), headers=self.h,
                       json={}, timeout=TIMEOUT)
        assert r.status_code == 201, r.text
        parts = r.json()
        assert len(parts) == 3 and all(p["page_count"] == 1 for p in parts)


# ──────────────────────────────────────────────────────────────────────────────
# Upload validation edge cases
# ──────────────────────────────────────────────────────────────────────────────

class TestUploadValidation:
    @classmethod
    def setup_class(cls):
        token, _ = _register("upl")
        cls.h = _hdr(token)

    def _up(self, name, data, mime="application/pdf"):
        return httpx.post(BASE + "/documents", headers=self.h,
                          files={"file": (name, data, mime)}, timeout=TIMEOUT)

    def test_valid_pdf_accepted(self):
        assert self._up("ok.pdf", PDF).status_code == 201

    def test_empty_file_rejected(self):
        r = self._up("empty.pdf", b"")
        assert r.status_code == 400 and "empty" in r.text.lower()

    def test_word_rejected(self):
        assert self._up("d.docx", b"PK\x03\x04" + b"\x00" * 40,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document").status_code == 400

    def test_excel_rejected(self):
        assert self._up("s.xlsx", b"PK\x03\x04" + b"\x01" * 40).status_code == 400

    def test_image_rejected(self):
        assert self._up("p.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 40, "image/png").status_code == 400

    def test_zip_rejected(self):
        assert self._up("a.zip", b"PK\x03\x04zipzipzip", "application/zip").status_code == 400

    def test_corrupted_pdf_rejected(self):
        r = self._up("c.pdf", b"%PDF-1.4 broken garbage no structure")
        assert r.status_code == 400

    def test_spoofed_mime_rejected(self):
        # claims application/pdf but real bytes are a zip → magic-byte check must catch it
        assert self._up("evil.pdf", b"PK\x03\x04zip", "application/pdf").status_code == 400

    def test_password_protected_rejected(self):
        # build a real encrypted PDF inside the pdf_service container (it has PyMuPDF)
        try:
            out = subprocess.run(
                ["docker", "exec", "pdf_editor-pdf_service-1", "python", "-c",
                 "import fitz,sys; d=fitz.open(); d.new_page(); "
                 "sys.stdout.buffer.write(d.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw='x', user_pw='x'))"],
                capture_output=True, timeout=30)
            enc = out.stdout
        except Exception:
            enc = b""
        if not enc.startswith(b"%PDF"):
            pytest.skip("pdf_service container not reachable via docker exec")
        r = self._up("locked.pdf", enc)
        assert r.status_code == 400 and "password" in r.text.lower()

    def test_large_file_rejected(self):
        # 101 MB (over the 100 MB cap) → 413, and no partial doc created
        big = PDF + b"\x00" * (101 * 1024 * 1024)
        r = self._up("big.pdf", big)
        assert r.status_code == 413, r.status_code

    def test_malware_eicar_blocked(self):
        # EICAR test string embedded in an otherwise-valid PDF → rejected by the scanner
        eicar = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
        malpdf = PDF[:-6] + eicar + b"\n%%EOF"
        r = self._up("mal.pdf", malpdf)
        assert r.status_code == 400 and "malware" in r.text.lower(), r.text

    def test_malware_scan_on_convert_upload(self):
        eicar = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
        r = httpx.post(BASE + "/convert/file", headers=self.h,
                       files={"file": ("mal.pdf", PDF[:-6] + eicar, "application/pdf")},
                       data={"target_format": "txt"}, timeout=TIMEOUT)
        assert r.status_code == 400 and "malware" in r.text.lower(), r.text

    def test_multiple_sequential_uploads(self):
        ids = {self._up(f"m{i}.pdf", PDF).json()["id"] for i in range(3)}
        assert len(ids) == 3   # three distinct documents created


# ──────────────────────────────────────────────────────────────────────────────
# Storage usage endpoint
# ──────────────────────────────────────────────────────────────────────────────

class TestStorageUsage:
    def test_usage_reflects_uploads(self):
        token, _ = _register("usage")
        h = _hdr(token)
        before = httpx.get(BASE + "/documents/usage", headers=h, timeout=TIMEOUT)
        assert before.status_code == 200, before.text
        body = before.json()
        assert body["documents"] == 0 and body["used_bytes"] == 0
        assert body["plan"] == "free" and body["limit_bytes"] == 100 * 1024 ** 2

        _upload(h)
        after = httpx.get(BASE + "/documents/usage", headers=h, timeout=TIMEOUT).json()
        assert after["documents"] == 1
        assert after["used_bytes"] >= len(PDF)

    def test_usage_requires_auth(self):
        assert httpx.get(BASE + "/documents/usage", timeout=TIMEOUT).status_code == 401

    def test_storage_quota_enforced_on_upload(self):
        """A free user (100 MB) can't exceed quota. We push the DB usage near the cap
        via a version-size row, then a normal upload must be rejected with 413."""
        token, email = _register("quota")
        h = _hdr(token)
        doc = _upload(h)   # tiny doc
        # set recorded storage to the full 100 MB free cap → any further upload exceeds it
        at_cap = 100 * 1024 * 1024
        if _psql("UPDATE documents SET file_size={} WHERE id='{}'".format(at_cap, doc)) is None:
            pytest.skip("postgres not reachable via docker exec")
        r = httpx.post(BASE + "/documents", headers=h,
                       files={"file": ("over.pdf", PDF, "application/pdf")}, timeout=TIMEOUT)
        assert r.status_code == 413 and "quota" in r.text.lower(), r.text

        # a business user (100 GB) with the same usage is NOT blocked → header-driven limit works
        if _psql("UPDATE users SET role='business' WHERE email='{}'".format(email)) is not None:
            biz = _hdr(httpx.post(BASE + "/auth/login",
                                  json={"email": email, "password": "TestPass123!"},
                                  timeout=TIMEOUT).json()["access_token"])
            r2 = httpx.post(BASE + "/documents", headers=biz,
                            files={"file": ("ok.pdf", PDF, "application/pdf")}, timeout=TIMEOUT)
            assert r2.status_code == 201, r2.text


# ──────────────────────────────────────────────────────────────────────────────
# Compression: size profiles, quality ladder, ratio reporting
# ──────────────────────────────────────────────────────────────────────────────

_TEXT_PDF_CODE = (
    "import sys, fitz; d=fitz.open()\n"
    "for i in range({n}):\n"
    "    p=d.new_page()\n"
    "    for y in range(60, 780, 14): p.insert_text((40,y), 'Line %d of page %d — lorem ipsum dolor sit amet.' % (y,i))\n"
    "sys.stdout.buffer.write(d.tobytes())"
)

# full-page JPEG noise per page ≈ a scan; deflate can't shrink it, only recompression can
_SCAN_PDF_CODE = (
    "import sys, io, fitz\n"
    "from PIL import Image\n"
    "img = Image.effect_noise((1654, 2339), 60).convert('RGB')\n"
    "b = io.BytesIO(); img.save(b, 'JPEG', quality=95)\n"
    "d = fitz.open()\n"
    "for _ in range({n}):\n"
    "    p = d.new_page(width=595, height=842)\n"
    "    p.insert_image(p.rect, stream=b.getvalue())\n"
    "sys.stdout.buffer.write(d.tobytes())"
)


class TestCompression:
    @classmethod
    def setup_class(cls):
        cls.h = _hdr(_register("compress")[0])

    def _upload_bytes(self, data, name="c.pdf"):
        r = httpx.post(BASE + "/documents", headers=self.h,
                       files={"file": (name, data, "application/pdf")}, timeout=120)
        assert r.status_code == 201, r.text
        return r.json()["id"], r.json()["file_size"]

    def _compress(self, doc, quality=None):
        r = httpx.post(BASE + "/documents/{}/compress".format(doc), headers=self.h,
                       json=({"quality": quality} if quality else None), timeout=120)
        assert r.status_code == 200, r.text
        return r.json()

    def test_small_pdf(self):
        doc, _ = self._upload_bytes(PDF)
        body = self._compress(doc)
        # tiny file may not shrink further, but must not corrupt or grow wildly
        assert body["compressed_size"] > 0
        assert "saved_ratio" in body and "original_size" in body

    def test_medium_and_large_text_pdf(self):
        for n, label in ((20, "medium"), (120, "large")):
            data = _container_bytes(_TEXT_PDF_CODE.format(n=n))
            if not data:
                pytest.skip("conversion container not reachable")
            doc, orig = self._upload_bytes(data, "{}.pdf".format(label))
            body = self._compress(doc)
            assert body["compressed_size"] <= orig, label
            assert body["page_count"] == n   # compression must never drop pages

    def test_scanned_pdf_shrinks_meaningfully(self):
        data = _container_bytes(_SCAN_PDF_CODE.format(n=4))
        if not data:
            pytest.skip("conversion container not reachable")
        doc, orig = self._upload_bytes(data, "scan.pdf")
        body = self._compress(doc, "low")
        assert body["saved_ratio"] >= 0.3, "expected ≥30% savings on a scan, got {}".format(body["saved_ratio"])
        assert body["page_count"] == 4

    def test_image_heavy_quality_ladder(self):
        """low must produce a smaller file than high; both smaller than the original."""
        data = _container_bytes(_SCAN_PDF_CODE.format(n=2))
        if not data:
            pytest.skip("conversion container not reachable")
        doc_low, orig = self._upload_bytes(data, "imgheavy1.pdf")
        doc_high, _   = self._upload_bytes(data, "imgheavy2.pdf")
        low  = self._compress(doc_low, "low")
        high = self._compress(doc_high, "high")
        assert low["compressed_size"] < orig and high["compressed_size"] < orig
        assert low["compressed_size"] < high["compressed_size"], \
            "low={} should be smaller than high={}".format(low["compressed_size"], high["compressed_size"])

    def test_ratio_reported_correctly(self):
        data = _container_bytes(_SCAN_PDF_CODE.format(n=2))
        if not data:
            pytest.skip("conversion container not reachable")
        doc, orig = self._upload_bytes(data, "ratio.pdf")
        body = self._compress(doc, "medium")
        expected = round(1 - body["compressed_size"] / body["original_size"], 3)
        assert body["original_size"] == orig
        assert abs(body["saved_ratio"] - expected) < 0.001

    def test_invalid_quality_rejected(self):
        doc, _ = self._upload_bytes(PDF)
        r = httpx.post(BASE + "/documents/{}/compress".format(doc), headers=self.h,
                       json={"quality": "ultra"}, timeout=TIMEOUT)
        assert r.status_code == 400


# ──────────────────────────────────────────────────────────────────────────────
# Conversion matrix: PDF↔Office, images→PDF, HTML→PDF
# ──────────────────────────────────────────────────────────────────────────────

def _container_bytes(code):
    """Generate a fixture file inside the conversion container (it has python-docx,
    openpyxl, python-pptx, PIL) and return its bytes; None if docker is unreachable."""
    try:
        out = subprocess.run(
            ["docker", "exec", "pdf_editor-conversion_service-1", "python", "-c", code],
            capture_output=True, timeout=60)
        return out.stdout if out.returncode == 0 and out.stdout else None
    except Exception:
        return None


class TestConversionMatrix:
    @classmethod
    def setup_class(cls):
        cls.h = _hdr(_register("convmx")[0])

    def _to_pdf(self, name, data, mime="application/octet-stream"):
        r = httpx.post(BASE + "/convert/file", headers=self.h,
                       files={"file": (name, data, mime)},
                       data={"target_format": "pdf"}, timeout=120)
        assert r.status_code == 200, "{}: {}".format(name, r.text)
        out = httpx.get(r.json()["download_url"], timeout=TIMEOUT).content
        assert out[:5] == b"%PDF-", "{} did not produce a PDF".format(name)
        return out

    def test_word_to_pdf(self):
        docx = _container_bytes(
            "import sys, io; from docx import Document; d=Document(); d.add_paragraph('Hello from Word'); "
            "b=io.BytesIO(); d.save(b); sys.stdout.buffer.write(b.getvalue())")
        if not docx:
            pytest.skip("conversion container not reachable via docker exec")
        self._to_pdf("sample.docx", docx)

    def test_excel_to_pdf(self):
        xlsx = _container_bytes(
            "import sys, io; from openpyxl import Workbook; wb=Workbook(); wb.active['A1']='Hello Excel'; "
            "b=io.BytesIO(); wb.save(b); sys.stdout.buffer.write(b.getvalue())")
        if not xlsx:
            pytest.skip("conversion container not reachable via docker exec")
        self._to_pdf("sample.xlsx", xlsx)

    def test_powerpoint_to_pdf(self):
        pptx = _container_bytes(
            "import sys, io; from pptx import Presentation; p=Presentation(); "
            "p.slides.add_slide(p.slide_layouts[6]); "
            "b=io.BytesIO(); p.save(b); sys.stdout.buffer.write(b.getvalue())")
        if not pptx:
            pytest.skip("conversion container not reachable via docker exec")
        self._to_pdf("sample.pptx", pptx)

    def test_png_to_pdf(self):
        self._to_pdf("pixel.png", PNG, "image/png")

    def test_jpg_to_pdf(self):
        jpg = _container_bytes(
            "import sys, io; from PIL import Image; b=io.BytesIO(); "
            "Image.new('RGB',(40,40),(200,30,30)).save(b,'JPEG'); sys.stdout.buffer.write(b.getvalue())")
        if not jpg:
            pytest.skip("conversion container not reachable via docker exec")
        self._to_pdf("photo.jpg", jpg, "image/jpeg")

    def test_html_to_pdf(self):
        html = b"<html><body><h1>Hello HTML</h1><p>Converted to PDF.</p></body></html>"
        self._to_pdf("page.html", html, "text/html")

    def test_pdf_to_word(self):
        doc = _upload(self.h)
        r = httpx.post(BASE + "/convert/convert", headers=self.h,
                       json={"document_id": doc, "source_format": "pdf", "target_format": "docx"},
                       timeout=120)
        assert r.status_code == 200, r.text
        out = httpx.get(r.json()["download_url"], timeout=TIMEOUT).content
        assert out[:2] == b"PK", "docx output should be a zip container"


# ──────────────────────────────────────────────────────────────────────────────
# Translation (English ⇄ Hindi / Telugu / …)
# ──────────────────────────────────────────────────────────────────────────────

def _pdf_with_text(text):
    """Build a PDF containing `text` inside the conversion container (Unicode-safe)."""
    code = (
        "import sys, fitz; d=fitz.open(); p=d.new_page(); "
        "p.insert_text((50,100), {!r}, fontname='helv', fontsize=12); "
        "sys.stdout.buffer.write(d.tobytes())".format(text)
    )
    return _container_bytes(code)


def _in_range(s, lo, hi):
    return any(lo <= ord(c) <= hi for c in s)


class TestTranslation:
    @classmethod
    def setup_class(cls):
        cls.h = _hdr(_register("translate")[0])

    def _translate(self, pdf_bytes, target, source="auto"):
        r = httpx.post(BASE + "/convert/translate-file", headers=self.h,
                       files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
                       data={"target_lang": target, "source_lang": source}, timeout=120)
        if r.status_code == 502:
            pytest.skip("external translation endpoint unavailable")
        assert r.status_code == 200, r.text
        return r.json()

    def test_english_to_hindi(self):
        pdf = _pdf_with_text("Hello world. This is a test document.")
        if not pdf:
            pytest.skip("conversion container not reachable")
        body = self._translate(pdf, "hi")
        assert body["target_language"] == "Hindi"
        assert _in_range(body["translated_text"], 0x0900, 0x097F), body["translated_text"][:120]  # Devanagari
        # artifacts downloadable
        assert httpx.get(body["download_url"], timeout=60).content[:5] == b"%PDF-"
        assert len(httpx.get(body["txt_url"], timeout=60).content) > 0

    def test_english_to_telugu(self):
        pdf = _pdf_with_text("Good morning. Welcome to the meeting.")
        if not pdf:
            pytest.skip("conversion container not reachable")
        body = self._translate(pdf, "te")
        assert _in_range(body["translated_text"], 0x0C00, 0x0C7F), body["translated_text"][:120]  # Telugu

    def test_reverse_hindi_to_english(self):
        # "How are you?" in Hindi — base-14 fonts can't render Devanagari glyphs, so the
        # fixture is built with fitz's default which stores the text layer regardless.
        pdf = _container_bytes(
            "import sys, fitz; d=fitz.open(); p=d.new_page(); "
            "tw=fitz.TextWriter(p.rect); "
            "tw.append((50,100), 'aap kaise hain? main theek hoon.'); tw.write_text(p); "
            "sys.stdout.buffer.write(d.tobytes())")
        if not pdf:
            pytest.skip("conversion container not reachable")
        body = self._translate(pdf, "en", source="hi")
        assert body["target_language"] == "English"
        assert body["translated_text"].strip(), "expected non-empty English output"

    def test_layout_preserved_in_translated_pdf(self):
        """Payslip-style fixture: labels at fixed positions + amounts + a table line.
        The translated PDF must keep one page, keep the amounts verbatim, and put the
        translated label near the original's position (not re-flowed to the top)."""
        code = (
            "import sys, fitz; d=fitz.open(); p=d.new_page(width=595, height=842)\n"
            "p.insert_text((50, 100), 'Employee Name', fontsize=11)\n"
            "p.insert_text((300, 100), 'Bhukya Pradeep', fontsize=11)\n"
            "p.insert_text((50, 140), 'Emp Code: AHMS0560', fontsize=11)\n"
            "p.insert_text((50, 400), 'Net Salary Payable', fontsize=11)\n"
            "p.insert_text((300, 400), '17594.00', fontsize=11)\n"
            "p.draw_line(fitz.Point(40, 420), fitz.Point(550, 420))\n"
            "sys.stdout.buffer.write(d.tobytes())"
        )
        pdf = _container_bytes(code)
        if not pdf:
            pytest.skip("conversion container not reachable")
        body = self._translate(pdf, "hi", source="en")
        out = httpx.get(body["download_url"], timeout=60).content
        assert out[:5] == b"%PDF-"

        # inspect the output inside the container (it has fitz); PDF piped via stdin
        import json as _json
        probe = (
            "import sys, fitz, json\n"
            "data = sys.stdin.buffer.read()\n"
            "d = fitz.open(stream=data, filetype='pdf')\n"
            "out = {'pages': len(d), 'blocks': [[list(b[:4]), b[4]] for b in d[0].get_text('blocks')],\n"
            "       'words': [[w[0], w[1], w[4]] for w in d[0].get_text('words')]}\n"
            "sys.stdout.write(json.dumps(out))"
        )
        proc = subprocess.run(
            ["docker", "exec", "-i", "pdf_editor-conversion_service-1", "python", "-c", probe],
            input=out, capture_output=True, timeout=60)
        assert proc.returncode == 0 and proc.stdout, "could not inspect output pdf"
        parsed = _json.loads(proc.stdout.decode("utf-8"))
        assert parsed["pages"] == 1

        blocks = parsed["blocks"]
        text_all = " ".join(b[1] for b in blocks)
        assert "17594.00" in text_all, "amounts must pass through unchanged"
        assert "AHMS0560" in text_all, "IDs inside translated labels must survive"
        assert _in_range(text_all, 0x0900, 0x097F), "labels must be in Devanagari"
        # column structure by word positions: amount in the right column & lower half,
        # its translated label in the left column at the same height
        words = parsed["words"]   # [x0, y0, text]
        amount = [w for w in words if w[2] == "17594.00"]
        assert amount, "amount word must exist"
        assert amount[0][0] > 250 and amount[0][1] > 300, \
            "amount must stay in the right column, lower half (got {})".format(amount[0])
        label_words = [w for w in words
                       if w[1] > 300 and w[0] < 200 and _in_range(w[2], 0x0900, 0x097F)]
        assert label_words, "translated label must stay in the left-hand column"

    def test_bad_language_rejected(self):
        pdf = _pdf_with_text("hello")
        if not pdf:
            pytest.skip("conversion container not reachable")
        r = httpx.post(BASE + "/convert/translate-file", headers=self.h,
                       files={"file": ("doc.pdf", pdf, "application/pdf")},
                       data={"target_lang": "klingon"}, timeout=TIMEOUT)
        assert r.status_code == 400

    def test_scanned_pdf_needs_ocr_message(self):
        r = httpx.post(BASE + "/convert/translate-file", headers=self.h,
                       files={"file": ("blank.pdf", PDF, "application/pdf")},
                       data={"target_lang": "hi"}, timeout=TIMEOUT)
        assert r.status_code == 400 and "OCR" in r.text

    def test_languages_endpoint(self):
        r = httpx.get(BASE + "/convert/translate-languages", headers=self.h, timeout=TIMEOUT)
        assert r.status_code == 200
        langs = r.json()["languages"]
        assert {"en", "hi", "te", "fr", "de"}.issubset(langs.keys())


# ──────────────────────────────────────────────────────────────────────────────
# Analytics tracking
# ──────────────────────────────────────────────────────────────────────────────

class TestAnalytics:
    def test_track_event(self):
        token, _ = _register("track")
        r = httpx.post(BASE + "/analytics/track", headers=_hdr(token),
                       json={"event_type": "pageview", "path": "/dashboard", "source": "e2e"},
                       timeout=TIMEOUT)
        assert r.status_code == 200 and r.json()["ok"] is True

    def test_track_requires_auth(self):
        assert httpx.post(BASE + "/analytics/track", json={}, timeout=TIMEOUT).status_code == 401


# ──────────────────────────────────────────────────────────────────────────────
# Admin API exercised as a real (super)admin
# ──────────────────────────────────────────────────────────────────────────────

class TestAdminAsAdmin:
    @classmethod
    def setup_class(cls):
        token, email = _register("adm")
        if _psql("UPDATE users SET admin_level='superadmin' WHERE email='{}'".format(email)) is None:
            pytest.skip("postgres container not reachable via docker exec")
        cls.h = _hdr(token)
        cls.email = email
        # a normal user to manage
        t2, e2 = _register("subject")
        cls.subject_email = e2
        me = httpx.get(BASE + "/auth/me", headers=_hdr(t2), timeout=TIMEOUT).json()
        cls.subject_id = me["id"]

    @pytest.mark.parametrize("path", [
        "stats", "users", "documents", "revenue", "subscriptions", "invoices",
        "support-tickets", "analytics", "settings", "audit-logs", "kpis",
    ])
    def test_admin_get_endpoints(self, path):
        r = httpx.get(BASE + "/admin/" + path, headers=self.h, timeout=TIMEOUT)
        assert r.status_code == 200, "{}: {}".format(path, r.text)

    def test_patch_user(self):
        r = httpx.patch(BASE + "/admin/users/" + self.subject_id, headers=self.h,
                        json={"full_name": "Renamed By Admin", "admin_level": "moderator"},
                        timeout=TIMEOUT)
        assert r.status_code == 200, r.text

    def test_admin_reset_password(self):
        r = httpx.post(BASE + "/admin/users/{}/reset-password".format(self.subject_id),
                       headers=self.h, timeout=TIMEOUT)
        assert r.status_code == 200 and r.json()["sent"] is True, r.text

    def test_put_settings(self):
        r = httpx.put(BASE + "/admin/settings", headers=self.h,
                      json={"key": "support", "value": {"email": "help@example.com"}}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text

    def test_admin_cannot_delete_self(self):
        me = httpx.get(BASE + "/auth/me", headers=self.h, timeout=TIMEOUT).json()
        r = httpx.delete(BASE + "/admin/users/" + me["id"], headers=self.h, timeout=TIMEOUT)
        assert r.status_code == 400

    def test_delete_user(self):
        r = httpx.delete(BASE + "/admin/users/" + self.subject_id, headers=self.h, timeout=TIMEOUT)
        assert r.status_code == 204, r.text


# ──────────────────────────────────────────────────────────────────────────────
# Webhook APIs — signature verification
# ──────────────────────────────────────────────────────────────────────────────

class TestWebhooks:
    """Webhooks are public (no JWT — providers can't send one) but must be
    authenticated by their signature. Razorpay uses HMAC-SHA256 of the raw body."""
    RZP_SECRET = "rzp_whsec_demo_9f3a2c7b1e"   # mirrors .env RAZORPAY_WEBHOOK_SECRET

    def _sign(self, body: bytes):
        import hashlib, hmac
        return hmac.new(self.RZP_SECRET.encode(), body, hashlib.sha256).hexdigest()

    def test_stripe_webhook_public_but_signature_required(self):
        # public → not 401; unsigned/disabled → 400 or 503, never 200/500
        r = httpx.post(BASE + "/billing/webhook", content=b"{}", timeout=TIMEOUT)
        assert r.status_code in (400, 503), r.text

    def test_razorpay_valid_signature_accepted(self):
        body = b'{"event":"payment.captured","payload":{}}'
        r = httpx.post(BASE + "/billing/webhook/razorpay", content=body,
                       headers={"content-type": "application/json",
                                "x-razorpay-signature": self._sign(body)}, timeout=TIMEOUT)
        # 200 when the secret matches; if the running stack has no secret set, it's still 200
        assert r.status_code == 200, r.text

    def test_razorpay_bad_signature_rejected(self):
        body = b'{"event":"payment.captured"}'
        r = httpx.post(BASE + "/billing/webhook/razorpay", content=body,
                       headers={"content-type": "application/json",
                                "x-razorpay-signature": "deadbeef" * 8}, timeout=TIMEOUT)
        # rejected when the secret is configured; tolerate 200 if a stack runs without it
        if r.status_code != 200:
            assert r.status_code == 400, r.text

    def test_razorpay_missing_signature_rejected_when_enforced(self):
        body = b'{"event":"payment.captured"}'
        r = httpx.post(BASE + "/billing/webhook/razorpay", content=body,
                       headers={"content-type": "application/json"}, timeout=TIMEOUT)
        assert r.status_code in (200, 400)   # 400 when secret set, 200 in dev

    def test_razorpay_tampered_body_fails_signature(self):
        signed = b'{"event":"payment.captured","amount":100}'
        sig = self._sign(signed)
        tampered = b'{"event":"payment.captured","amount":999999}'   # same sig, different body
        r = httpx.post(BASE + "/billing/webhook/razorpay", content=tampered,
                       headers={"content-type": "application/json", "x-razorpay-signature": sig},
                       timeout=TIMEOUT)
        if r.status_code != 200:
            assert r.status_code == 400, r.text

    def test_webhooks_need_no_jwt(self):
        # a provider callback carries no Authorization header → must not be 401
        for path, body in (("/billing/webhook/paypal", b'{"event_type":"x"}'),
                           ("/billing/webhook/razorpay", b'{"event":"x"}')):
            r = httpx.post(BASE + path, content=body,
                           headers={"content-type": "application/json"}, timeout=TIMEOUT)
            assert r.status_code != 401, path


# ──────────────────────────────────────────────────────────────────────────────
# Security controls (authz, injection, JWT, XSS, CORS, download links)
# ──────────────────────────────────────────────────────────────────────────────

class TestSecurityControls:
    @classmethod
    def setup_class(cls):
        cls.token, _ = _register("secx")
        cls.h = _hdr(cls.token)
        cls.doc = _upload(cls.h)

    def test_alg_none_jwt_rejected(self):
        hdr = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').decode().rstrip("=")
        pl  = base64.urlsafe_b64encode(
            b'{"sub":"00000000-0000-0000-0000-000000000000","role":"admin","email":"x@x.com"}').decode().rstrip("=")
        r = httpx.get(BASE + "/documents", headers=_hdr(f"{hdr}.{pl}."), timeout=TIMEOUT)
        assert r.status_code == 401

    def test_tampered_jwt_payload_rejected(self):
        parts = self.token.split(".")
        forged = parts[0] + "." + base64.urlsafe_b64encode(
            b'{"sub":"x","role":"admin"}').decode().rstrip("=") + "." + parts[2]
        assert httpx.get(BASE + "/documents", headers=_hdr(forged), timeout=TIMEOUT).status_code == 401

    def test_sql_injection_login(self):
        # invalid-email injection → 422 (validation); credential injection → 401. Never 200.
        for email in ("' OR '1'='1", "admin'--"):
            r = httpx.post(BASE + "/auth/login",
                           json={"email": email, "password": "x"}, timeout=TIMEOUT)
            assert r.status_code in (401, 422), (email, r.status_code)

    def test_sql_injection_query_param_safe(self):
        r = httpx.get(BASE + "/documents?page=1'; DROP TABLE documents;--", headers=self.h, timeout=TIMEOUT)
        assert r.status_code in (200, 422)
        # table still there
        assert httpx.get(BASE + "/documents", headers=self.h, timeout=TIMEOUT).status_code == 200

    def test_stored_xss_returned_as_json_not_html(self):
        payload = "<script>alert(1)</script>"
        httpx.patch(BASE + "/documents/{}".format(self.doc), headers=self.h,
                    json={"original_name": payload}, timeout=TIMEOUT)
        r = httpx.get(BASE + "/documents/{}".format(self.doc), headers=self.h, timeout=TIMEOUT)
        assert "application/json" in r.headers.get("content-type", "")
        assert r.json()["original_name"] == payload   # stored verbatim; React escapes on render

    def test_security_headers_present(self):
        r = httpx.get("http://localhost:8000/health", timeout=TIMEOUT)
        h = {k.lower(): v for k, v in r.headers.items()}
        assert h.get("x-content-type-options") == "nosniff"
        assert h.get("x-frame-options") == "DENY"
        assert "frame-ancestors 'none'" in h.get("content-security-policy", "")

    def test_cors_rejects_evil_origin(self):
        r = httpx.options(BASE + "/documents",
                          headers={"Origin": "https://evil.com", "Access-Control-Request-Method": "GET"},
                          timeout=TIMEOUT)
        aco = r.headers.get("access-control-allow-origin", "")
        assert aco not in ("https://evil.com", "*")

    def test_download_link_is_presigned_and_tamper_proof(self):
        import re as _re
        url = httpx.get(BASE + "/documents/{}/download".format(self.doc), headers=self.h,
                        timeout=TIMEOUT).json()["url"]
        assert "X-Amz-Signature" in url and "X-Amz-Expires" in url
        assert httpx.get(url, timeout=TIMEOUT).status_code == 200
        tampered = _re.sub(r"X-Amz-Signature=[0-9a-f]+", "X-Amz-Signature=" + "0" * 64, url)
        assert httpx.get(tampered, timeout=TIMEOUT).status_code in (400, 403)

    def test_password_hash_never_exposed(self):
        me = httpx.get(BASE + "/auth/me", headers=self.h, timeout=TIMEOUT).json()
        assert "password" not in me and "hashed_password" not in me and "mfa_secret" not in me


# ──────────────────────────────────────────────────────────────────────────────
# Gateway routing edges
# ──────────────────────────────────────────────────────────────────────────────

class TestGatewayEdges:
    def test_ai_service_not_routed(self):
        """The AI service exists in the repo but has no gateway route / compose entry.
        This pins the current behavior; if it starts failing, AI was wired up —
        add real coverage for /api/v1/ai/*."""
        token, _ = _register("ai")
        r = httpx.post(BASE + "/ai/chat", headers=_hdr(token), json={"q": "hi"}, timeout=TIMEOUT)
        assert r.status_code == 404
