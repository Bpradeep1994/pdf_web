"""
Billing & Subscriptions (Stripe) — Phase 3.

Hosted in auth_service (owns users + the canonical subscriptions/invoices tables).
Feature-flagged: with no STRIPE_SECRET_KEY the read endpoints still work (plans,
current subscription, invoices) and the action endpoints return a clean 503
("billing not configured") instead of erroring. Activates fully when keys are set.

Endpoints (mounted at /api/v1/billing):
  GET  /plans          - plan catalogue (+ whether billing is enabled)
  GET  /subscription   - current user's subscription (seeded 'free' on signup)
  GET  /invoices       - current user's invoices
  POST /checkout       - create a Stripe Checkout session for a plan
  POST /portal         - create a Stripe billing-portal session
  POST /webhook        - Stripe webhook (public; signature-verified) → syncs DB
"""
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from shared.audit import record as audit
from models import User
from routes import _get_current_user

billing_router = APIRouter()

STRIPE_SECRET_KEY     = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
PAYPAL_WEBHOOK_ID       = os.getenv("PAYPAL_WEBHOOK_ID", "")
APP_URL               = os.getenv("NEXT_PUBLIC_APP_URL", "http://localhost:3000")

# ── Razorpay (India — settles to an Indian bank account) ──────────────────────
RAZORPAY_KEY_ID     = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
RAZORPAY_ENABLED    = bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET and "..." not in RAZORPAY_KEY_ID)
RAZORPAY_CURRENCY   = os.getenv("RAZORPAY_CURRENCY", "INR")
# Monthly prices in the smallest currency unit (paise for INR). Set real prices via env.
RAZORPAY_PRICES = {
    "pro":      int(os.getenv("RAZORPAY_PRICE_PRO",      "29900")),   # ₹299 / month
    "business": int(os.getenv("RAZORPAY_PRICE_BUSINESS", "99900")),   # ₹999 / month
}


def _razorpay_amount(plan: str, interval: str) -> int:
    base = RAZORPAY_PRICES.get(plan, 0)
    if interval == "yearly":   return base * 10     # 2 months free
    if interval == "lifetime": return base * 30
    return base


def _looks_real_key(k: str) -> bool:
    # Reject placeholders like "sk_test_..." — only a plausibly real key counts.
    return bool(k) and k.startswith("sk_") and "..." not in k and len(k) > 24


# Live Stripe only when we have a real key AND both price IDs; otherwise demo (dev) checkout.
BILLING_ENABLED = (
    _looks_real_key(STRIPE_SECRET_KEY)
    and bool(os.getenv("STRIPE_PRICE_PRO"))
    and bool(os.getenv("STRIPE_PRICE_BUSINESS"))
)

PLANS = {
    "free":       {"name": "Free",       "price_cents": 0,   "price_id": None},
    "pro":        {"name": "Pro",        "price_cents": 100, "price_id": os.getenv("STRIPE_PRICE_PRO", "")},
    "business":   {"name": "Business",   "price_cents": 500, "price_id": os.getenv("STRIPE_PRICE_BUSINESS", "")},
    "enterprise": {"name": "Enterprise", "price_cents": None, "price_id": None},
}

if BILLING_ENABLED:
    import stripe
    stripe.api_key = STRIPE_SECRET_KEY


def _require_enabled():
    if not BILLING_ENABLED:
        raise HTTPException(status_code=503, detail="Billing is not configured")


# ── Reads (work without Stripe keys) ──────────────────────────────────────────

@billing_router.get("/plans")
async def list_plans():
    return {
        "enabled": BILLING_ENABLED,
        "plans": [
            {"id": pid, "name": p["name"], "price_cents": p["price_cents"]}
            for pid, p in PLANS.items()
        ],
    }


@billing_router.get("/subscription")
async def get_subscription(current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(text(
        "SELECT plan, status, interval, current_period_end, cancelled_at "
        "FROM subscriptions WHERE user_id = CAST(:u AS uuid)"), {"u": str(current_user.id)})).mappings().first()
    if not row:
        return {"plan": "free", "status": "active"}
    return {
        "plan": row["plan"], "status": row["status"], "interval": row["interval"],
        "current_period_end": row["current_period_end"].isoformat() if row["current_period_end"] else None,
        "cancelled_at": row["cancelled_at"].isoformat() if row["cancelled_at"] else None,
    }


@billing_router.get("/invoices")
async def list_invoices(current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(text(
        "SELECT stripe_invoice_id, amount_paid, currency, status, invoice_url, created_at "
        "FROM invoices WHERE user_id = CAST(:u AS uuid) ORDER BY created_at DESC LIMIT 50"),
        {"u": str(current_user.id)})).mappings().all()
    return [
        {"stripe_invoice_id": r["stripe_invoice_id"], "amount_paid": r["amount_paid"],
         "currency": r["currency"], "status": r["status"], "invoice_url": r["invoice_url"],
         "created_at": r["created_at"].isoformat() if r["created_at"] else None}
        for r in rows
    ]


# ── Actions (require Stripe keys) ─────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan:     str
    interval: str = "monthly"          # monthly | yearly | lifetime
    provider: str = "stripe"           # stripe | paypal | razorpay | applepay | upi
    method:   str = "card"             # card | upi | netbanking | wallet | paypal
    card_brand: str | None = None      # visa | mastercard | amex | discover | jcb | diners


# Providers the platform supports (configured = real keys present, else demo).
PROVIDERS = ["stripe", "paypal", "razorpay", "applepay", "upi"]


def _amount_cents(plan_key: str, interval: str) -> int:
    base = PLANS.get(plan_key, {}).get("price_cents") or 0
    if interval == "yearly":   return base * 10     # 2 months free
    if interval == "lifetime": return base * 30
    return base


async def _pay_event(db, user_id, event_type, *, provider=None, amount_cents=None, currency="usd", data=None):
    import json
    await db.execute(text(
        "INSERT INTO payment_events (id, user_id, provider, event_type, amount_cents, currency, data) "
        "VALUES (uuid_generate_v4(), CAST(:u AS uuid), :pv, :et, :amt, :cur, CAST(:d AS jsonb))"),
        {"u": str(user_id) if user_id is not None else None, "pv": provider, "et": event_type,
         "amt": amount_cents, "cur": currency, "d": json.dumps(data or {})})


async def _ensure_customer(current_user: User, db: AsyncSession) -> str:
    row = (await db.execute(text(
        "SELECT stripe_customer_id FROM subscriptions WHERE user_id = CAST(:u AS uuid)"),
        {"u": str(current_user.id)})).mappings().first()
    if row and row["stripe_customer_id"]:
        return row["stripe_customer_id"]
    customer = stripe.Customer.create(email=current_user.email, metadata={"user_id": str(current_user.id)})
    await db.execute(text(
        "UPDATE subscriptions SET stripe_customer_id = :c WHERE user_id = CAST(:u AS uuid)"),
        {"c": customer.id, "u": str(current_user.id)})
    return customer.id


@billing_router.post("/checkout")
async def create_checkout(body: CheckoutRequest, request: Request,
                          current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    plan = PLANS.get(body.plan)
    if not plan or plan["price_cents"] in (0, None):
        raise HTTPException(status_code=400, detail="That plan is not purchasable")
    # Dev/demo mode (no Stripe keys): route to the built-in mock checkout page.
    if not BILLING_ENABLED:
        return {"checkout_url": f"{APP_URL}/billing/checkout?plan={body.plan}&interval={body.interval}", "dev": True}
    if not plan["price_id"]:
        raise HTTPException(status_code=400, detail="That plan is not purchasable")
    customer_id = await _ensure_customer(current_user, db)
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": plan["price_id"], "quantity": 1}],
        success_url=f"{APP_URL}/billing?status=success",
        cancel_url=f"{APP_URL}/billing?status=cancelled",
        metadata={"user_id": str(current_user.id), "plan": body.plan},
    )
    await audit(db, action="billing.checkout_created", user_id=current_user.id, request=request,
                metadata={"plan": body.plan})
    return {"checkout_url": session.url}


async def _activate(db: AsyncSession, current_user: User, body: "CheckoutRequest", request: Request | None = None):
    """Mark the plan active + record payment / method / audit event (demo path)."""
    import uuid as _uuid
    lifetime = body.interval == "lifetime"
    db_interval = None if lifetime else ("yearly" if body.interval == "yearly" else "monthly")
    trial_days = 14
    status = "active"
    period_end_sql = "NULL" if lifetime else (
        "now() + interval '1 year'" if body.interval == "yearly" else "now() + interval '1 month'")

    res = await db.execute(text(
        f"UPDATE subscriptions SET plan = :p, status = '{status}', interval = :iv, provider = :pv, "
        f"lifetime = :lt, cancel_at_period_end = FALSE, current_period_start = now(), "
        f"current_period_end = {period_end_sql}, cancelled_at = NULL, updated_at = now() "
        f"WHERE user_id = CAST(:u AS uuid)"),
        {"p": body.plan, "iv": db_interval, "pv": body.provider, "lt": lifetime, "u": str(current_user.id)})
    if res.rowcount == 0:
        await db.execute(text(
            f"INSERT INTO subscriptions (id, user_id, plan, status, interval, provider, lifetime, current_period_end) "
            f"VALUES (uuid_generate_v4(), CAST(:u AS uuid), :p, '{status}', :iv, :pv, :lt, {period_end_sql})"),
            {"u": str(current_user.id), "p": body.plan, "iv": db_interval, "pv": body.provider, "lt": lifetime})

    await db.execute(text("UPDATE users SET role = :r WHERE id = CAST(:u AS uuid)"),
                     {"r": body.plan, "u": str(current_user.id)})

    # record a payment + (saved) payment method + audit event
    amt = _amount_cents(body.plan, body.interval)
    pay_id = _uuid.uuid4()
    await db.execute(text(
        "INSERT INTO payments (id, user_id, stripe_payment_id, amount_cents, currency, status, provider, method, card_brand, description) "
        "VALUES (CAST(:id AS uuid), CAST(:u AS uuid), :sp, :amt, 'usd', 'succeeded', :pv, :m, :cb, :desc)"),
        {"id": str(pay_id), "u": str(current_user.id), "sp": f"demo_{pay_id}", "amt": amt,
         "pv": body.provider, "m": body.method, "cb": body.card_brand,
         "desc": f"{PLANS[body.plan]['name']} ({body.interval})"})
    if body.method == "card" and body.card_brand:
        await db.execute(text(
            "INSERT INTO payment_methods (id, user_id, provider, type, brand, last4, is_default) "
            "VALUES (uuid_generate_v4(), CAST(:u AS uuid), :pv, 'card', :b, '4242', TRUE)"),
            {"u": str(current_user.id), "pv": body.provider, "b": body.card_brand})
    # issue an invoice for the charge (Stripe does this via webhook; demo mode does it here
    # so the Invoices list works without live keys)
    await db.execute(text(
        "INSERT INTO invoices (id, user_id, stripe_invoice_id, amount_paid, currency, status) "
        "VALUES (uuid_generate_v4(), CAST(:u AS uuid), :inv, :amt, 'usd', 'paid')"),
        {"u": str(current_user.id), "inv": f"demo_inv_{pay_id}", "amt": amt})
    await _pay_event(db, current_user.id, "payment.succeeded", provider=body.provider, amount_cents=amt,
                     data={"plan": body.plan, "interval": body.interval, "method": body.method})
    await audit(db, action="billing.activated", user_id=current_user.id, request=request,
                metadata={"plan": body.plan, "interval": body.interval, "provider": body.provider})
    return {"plan": body.plan, "interval": body.interval, "lifetime": lifetime, "status": status, "amount_cents": amt}


@billing_router.post("/dev-activate")
async def dev_activate(body: CheckoutRequest, request: Request,
                       current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    if BILLING_ENABLED:
        raise HTTPException(status_code=400, detail="Use Stripe checkout")
    plan = PLANS.get(body.plan)
    if not plan or plan["price_cents"] in (0, None):
        raise HTTPException(status_code=400, detail="That plan is not purchasable")
    return await _activate(db, current_user, body, request)


# ── Payment OTP (sent to email + SMS) ─────────────────────────────────────────

import redis.asyncio as _aioredis   # noqa: E402
from emailer import send_payment_otp, send_sms  # noqa: E402

_REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
_otp_redis: "_aioredis.Redis | None" = None


async def _otp_store():
    global _otp_redis
    if _otp_redis is None:
        _otp_redis = _aioredis.from_url(_REDIS_URL, decode_responses=True)
    return _otp_redis


class SendOtpRequest(BaseModel):
    phone: str | None = None


@billing_router.post("/send-otp")
async def send_otp(body: SendOtpRequest, current_user: User = Depends(_get_current_user)):
    """Generate a 6-digit code, store it (5-min TTL), and send it to the user's email
    (+ SMS if a phone is given). Returns dev_otp only when neither channel can really deliver."""
    import secrets
    code = f"{secrets.randbelow(900000) + 100000}"
    try:
        r = await _otp_store()
        await r.setex(f"payotp:{current_user.id}", 300, code)
    except Exception:
        pass
    import emailer as _em
    send_payment_otp(current_user.email, code)        # real if SMTP set, else logged
    masked_phone = None
    if body.phone:
        send_sms(body.phone, f"PDFForge payment code: {code}")
        masked_phone = "•••• " + body.phone[-4:]
    delivered = _em.EMAIL_ENABLED or (body.phone and _em.SMS_ENABLED)
    resp = {"sent": True, "email": current_user.email, "phone": masked_phone,
            "channels": (["email"] if _em.EMAIL_ENABLED else []) + (["sms"] if (body.phone and _em.SMS_ENABLED) else [])}
    if not delivered:
        resp["dev_otp"] = code   # no real email/SMS configured → show it so the flow is testable
    return resp


class VerifyOtpRequest(CheckoutRequest):
    otp: str


@billing_router.post("/verify-otp")
async def verify_otp(body: VerifyOtpRequest, request: Request,
                     current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        r = await _otp_store()
        saved = await r.get(f"payotp:{current_user.id}")
    except Exception:
        saved = None
    if not saved or body.otp != saved:
        # record the failed attempt so it shows in payment history / admin
        import uuid as _u
        amt = _amount_cents(body.plan, body.interval) if body.plan in PLANS else 0
        try:
            await db.execute(text(
                "INSERT INTO payments (id, user_id, stripe_payment_id, amount_cents, currency, status, provider, method, description) "
                "VALUES (uuid_generate_v4(), CAST(:u AS uuid), :sp, :amt, 'usd', 'failed', :pv, :m, :d)"),
                {"u": str(current_user.id), "sp": f"failed_{_u.uuid4()}", "amt": amt,
                 "pv": body.provider, "m": body.method, "d": "Payment failed — incorrect verification code"})
            await _pay_event(db, current_user.id, "payment.failed", provider=body.provider,
                             amount_cents=amt, data={"reason": "invalid_otp"})
            await db.commit()   # the 400 below would otherwise roll this back
        except Exception:
            pass
        raise HTTPException(status_code=400, detail="Incorrect or expired code")
    try:
        await (await _otp_store()).delete(f"payotp:{current_user.id}")
    except Exception:
        pass
    plan = PLANS.get(body.plan)
    if not plan or plan["price_cents"] in (0, None):
        raise HTTPException(status_code=400, detail="That plan is not purchasable")
    return await _activate(db, current_user, body, request)


class PlanChange(BaseModel):
    plan: str


@billing_router.post("/change-plan")
async def change_plan(body: PlanChange, request: Request,
                      current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    """Upgrade or downgrade the current plan."""
    if body.plan not in PLANS or PLANS[body.plan]["price_cents"] is None:
        raise HTTPException(status_code=400, detail="Invalid plan")
    await db.execute(text(
        "UPDATE subscriptions SET plan = :p, status = 'active', updated_at = now() WHERE user_id = CAST(:u AS uuid)"),
        {"p": body.plan, "u": str(current_user.id)})
    await db.execute(text("UPDATE users SET role = :r WHERE id = CAST(:u AS uuid)"),
                     {"r": body.plan if body.plan != "enterprise" else "business", "u": str(current_user.id)})
    await _pay_event(db, current_user.id, "subscription.changed", data={"plan": body.plan})
    await audit(db, action="billing.plan_changed", user_id=current_user.id, request=request, metadata={"plan": body.plan})
    return {"plan": body.plan, "status": "active"}


@billing_router.post("/cancel")
async def cancel_subscription(request: Request, current_user: User = Depends(_get_current_user),
                              db: AsyncSession = Depends(get_db)):
    """Cancel at period end (keeps access until the period ends)."""
    await db.execute(text(
        "UPDATE subscriptions SET cancel_at_period_end = TRUE, cancelled_at = now(), updated_at = now() "
        "WHERE user_id = CAST(:u AS uuid)"), {"u": str(current_user.id)})
    await _pay_event(db, current_user.id, "subscription.cancel_scheduled", data={})
    await audit(db, action="billing.cancelled", user_id=current_user.id, request=request)
    return {"status": "active", "cancel_at_period_end": True}


@billing_router.post("/resume")
async def resume_subscription(request: Request, current_user: User = Depends(_get_current_user),
                              db: AsyncSession = Depends(get_db)):
    await db.execute(text(
        "UPDATE subscriptions SET cancel_at_period_end = FALSE, cancelled_at = NULL, updated_at = now() "
        "WHERE user_id = CAST(:u AS uuid)"), {"u": str(current_user.id)})
    await _pay_event(db, current_user.id, "subscription.resumed", data={})
    return {"status": "active", "cancel_at_period_end": False}


class RefundRequest(BaseModel):
    payment_id: str
    reason: str | None = None


@billing_router.post("/refund")
async def refund_payment(body: RefundRequest, request: Request,
                         current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    pay = (await db.execute(text(
        "SELECT id, amount_cents, currency, provider, status FROM payments "
        "WHERE id = CAST(:id AS uuid) AND user_id = CAST(:u AS uuid)"),
        {"id": body.payment_id, "u": str(current_user.id)})).mappings().first()
    if not pay:
        raise HTTPException(status_code=404, detail="Payment not found")
    if pay["status"] == "refunded":
        raise HTTPException(status_code=400, detail="Already refunded")
    await db.execute(text("UPDATE payments SET status = 'refunded' WHERE id = CAST(:id AS uuid)"), {"id": body.payment_id})
    await db.execute(text(
        "INSERT INTO refunds (id, payment_id, user_id, amount_cents, currency, reason, provider) "
        "VALUES (uuid_generate_v4(), CAST(:pid AS uuid), CAST(:u AS uuid), :amt, :cur, :rsn, :pv)"),
        {"pid": body.payment_id, "u": str(current_user.id), "amt": pay["amount_cents"],
         "cur": pay["currency"], "rsn": body.reason, "pv": pay["provider"]})
    await _pay_event(db, current_user.id, "payment.refunded", provider=pay["provider"],
                     amount_cents=pay["amount_cents"], data={"payment_id": body.payment_id})
    await audit(db, action="billing.refunded", user_id=current_user.id, request=request, metadata={"payment_id": body.payment_id})
    return {"payment_id": body.payment_id, "status": "refunded"}


@billing_router.get("/providers")
async def list_providers():
    return {"providers": PROVIDERS, "live": BILLING_ENABLED,
            "methods": ["card", "upi", "netbanking", "wallet", "paypal"],
            "cards": ["visa", "mastercard", "amex", "discover", "jcb", "diners"],
            # Razorpay live-checkout config for the frontend widget (key_id is public).
            "razorpay_enabled": RAZORPAY_ENABLED,
            "razorpay_key_id":  RAZORPAY_KEY_ID if RAZORPAY_ENABLED else "",
            "razorpay_currency": RAZORPAY_CURRENCY,
            "razorpay_prices": {k: _razorpay_amount(k, "monthly") for k in RAZORPAY_PRICES}}


@billing_router.get("/payment-methods")
async def list_payment_methods(current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(text(
        "SELECT id, provider, type, brand, last4, is_default, created_at FROM payment_methods "
        "WHERE user_id = CAST(:u AS uuid) ORDER BY created_at DESC"), {"u": str(current_user.id)})).mappings().all()
    return [{"id": str(r["id"]), "provider": r["provider"], "type": r["type"], "brand": r["brand"],
             "last4": r["last4"], "is_default": r["is_default"]} for r in rows]


@billing_router.get("/payments")
async def list_payments(current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(text(
        "SELECT id, amount_cents, currency, status, provider, method, card_brand, description, created_at "
        "FROM payments WHERE user_id = CAST(:u AS uuid) ORDER BY created_at DESC LIMIT 100"),
        {"u": str(current_user.id)})).mappings().all()
    return [{"id": str(r["id"]), "amount": round((r["amount_cents"] or 0) / 100, 2), "currency": r["currency"],
             "status": r["status"], "provider": r["provider"], "method": r["method"], "card_brand": r["card_brand"],
             "description": r["description"], "created_at": r["created_at"].isoformat() if r["created_at"] else None}
            for r in rows]


@billing_router.post("/portal")
async def create_portal(current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _require_enabled()
    customer_id = await _ensure_customer(current_user, db)
    session = stripe.billing_portal.Session.create(customer=customer_id, return_url=f"{APP_URL}/billing")
    return {"portal_url": session.url}


# ── Webhook (public; Stripe-signed) ───────────────────────────────────────────

async def _set_subscription(db: AsyncSession, customer_id: str, *, plan=None, status=None,
                            sub_id=None, period_end=None):
    sets, params = [], {"c": customer_id}
    if plan is not None:    sets.append("plan = CAST(:plan AS user_role)"); params["plan"] = plan
    if status is not None:  sets.append("status = CAST(:st AS subscription_status)"); params["st"] = status
    if sub_id is not None:  sets.append("stripe_subscription_id = :sid"); params["sid"] = sub_id
    if period_end is not None:
        sets.append("current_period_end = to_timestamp(:pe)"); params["pe"] = period_end
    sets.append("updated_at = now()")
    await db.execute(text(
        f"UPDATE subscriptions SET {', '.join(sets)} WHERE stripe_customer_id = :c"), params)


@billing_router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    _require_enabled()
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    typ  = event["type"]
    obj  = event["data"]["object"]

    if typ == "checkout.session.completed":
        await _set_subscription(db, obj["customer"], plan=obj.get("metadata", {}).get("plan"),
                                status="active", sub_id=obj.get("subscription"))
    elif typ in ("customer.subscription.updated", "customer.subscription.created"):
        status_map = {"active": "active", "trialing": "trialing", "past_due": "past_due",
                      "canceled": "cancelled", "unpaid": "past_due"}
        await _set_subscription(db, obj["customer"],
                                status=status_map.get(obj["status"], "active"),
                                sub_id=obj["id"], period_end=obj.get("current_period_end"))
    elif typ == "customer.subscription.deleted":
        await _set_subscription(db, obj["customer"], plan="free", status="cancelled")
    elif typ == "invoice.paid":
        await db.execute(text(
            "INSERT INTO invoices (id, user_id, stripe_invoice_id, amount_paid, currency, status, invoice_url) "
            "SELECT uuid_generate_v4(), s.user_id, :inv, :amt, :cur, 'paid', :url "
            "FROM subscriptions s WHERE s.stripe_customer_id = :c "
            "ON CONFLICT DO NOTHING"),
            {"inv": obj.get("id"), "amt": obj.get("amount_paid", 0), "cur": obj.get("currency", "usd"),
             "url": obj.get("hosted_invoice_url"), "c": obj["customer"]})
    elif typ in ("payment_intent.succeeded", "payment_intent.payment_failed"):
        status = "succeeded" if typ.endswith("succeeded") else "failed"
        await db.execute(text(
            "INSERT INTO payments (id, user_id, subscription_id, stripe_payment_id, amount_cents, currency, status) "
            "SELECT uuid_generate_v4(), s.user_id, s.id, :pid, :amt, :cur, :st "
            "FROM subscriptions s WHERE s.stripe_customer_id = :c "
            "ON CONFLICT (stripe_payment_id) DO UPDATE SET status = EXCLUDED.status"),
            {"pid": obj.get("id"), "amt": obj.get("amount", 0), "cur": obj.get("currency", "usd"),
             "st": status, "c": obj.get("customer")})

    return {"received": True}


# ── Razorpay live checkout (order → pay → verify) ─────────────────────────────
# Flow: frontend asks the backend to create an Order → opens Razorpay Checkout with
# it → user pays (card/UPI/netbanking) → Razorpay returns payment_id + signature →
# backend verifies the signature and activates the plan. The money lands in your
# Razorpay account and settles to your linked Indian bank account on Razorpay's
# payout schedule. The /webhook/razorpay handler below is the server-to-server
# backup confirmation.

import hashlib as _hashlib
import hmac as _hmac
import httpx as _httpx


class RazorpayOrderRequest(BaseModel):
    plan:     str
    interval: str = "monthly"


@billing_router.post("/razorpay/order")
async def razorpay_create_order(body: RazorpayOrderRequest,
                                current_user: User = Depends(_get_current_user)):
    if not RAZORPAY_ENABLED:
        raise HTTPException(status_code=503, detail="Razorpay is not configured")
    if body.plan not in RAZORPAY_PRICES:
        raise HTTPException(status_code=400, detail="That plan is not purchasable")
    amount = _razorpay_amount(body.plan, body.interval)
    try:
        async with _httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                "https://api.razorpay.com/v1/orders",
                auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET),
                json={"amount": amount, "currency": RAZORPAY_CURRENCY, "receipt": f"u_{current_user.id}",
                      "notes": {"user_id": str(current_user.id), "plan": body.plan, "interval": body.interval}},
            )
        r.raise_for_status()
    except Exception:
        raise HTTPException(status_code=502, detail="Could not create payment order")
    order = r.json()
    return {
        "order_id": order["id"], "amount": amount, "currency": RAZORPAY_CURRENCY,
        "key_id": RAZORPAY_KEY_ID, "plan_name": PLANS.get(body.plan, {}).get("name", body.plan),
        "email": current_user.email,
    }


class RazorpayVerifyRequest(CheckoutRequest):
    razorpay_order_id:   str
    razorpay_payment_id: str
    razorpay_signature:  str


@billing_router.post("/razorpay/verify")
async def razorpay_verify(body: RazorpayVerifyRequest, request: Request,
                          current_user: User = Depends(_get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """Verify the payment signature Razorpay returns to the browser, then activate the plan."""
    if not RAZORPAY_ENABLED:
        raise HTTPException(status_code=503, detail="Razorpay is not configured")
    expected = _hmac.new(
        RAZORPAY_KEY_SECRET.encode(),
        f"{body.razorpay_order_id}|{body.razorpay_payment_id}".encode(),
        _hashlib.sha256,
    ).hexdigest()
    if not _hmac.compare_digest(expected, body.razorpay_signature or ""):
        await _pay_event(db, current_user.id, "payment.failed", provider="razorpay",
                         data={"reason": "bad_signature", "order": body.razorpay_order_id})
        await db.commit()
        raise HTTPException(status_code=400, detail="Payment verification failed")
    body.provider = "razorpay"
    result = await _activate(db, current_user, body, request)
    await db.commit()
    return result


# ── Other providers ───────────────────────────────────────────────────────────

@billing_router.post("/webhook/razorpay")
async def razorpay_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Razorpay webhook. When RAZORPAY_WEBHOOK_SECRET is set the X-Razorpay-Signature
    (HMAC-SHA256 of the raw body) is verified and a bad/missing signature is rejected.
    Unset (dev) → accepted so the integration can be exercised without live keys."""
    import hashlib
    import hmac
    import json as _json

    raw = await request.body()
    if RAZORPAY_WEBHOOK_SECRET:
        sig = request.headers.get("x-razorpay-signature", "")
        expected = hmac.new(RAZORPAY_WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
        if not sig or not hmac.compare_digest(sig, expected):
            raise HTTPException(status_code=400, detail="Invalid webhook signature")

    try:
        payload = _json.loads(raw or b"{}")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event = payload.get("event", "event")
    await _pay_event(db, None, f"razorpay.{event}", provider="razorpay", data={"event": event})
    await db.commit()
    return {"received": True}


@billing_router.post("/webhook/paypal")
async def paypal_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """PayPal webhook. When PAYPAL_WEBHOOK_ID is configured we require PayPal's
    transmission-signature headers and verify them via PayPal's verify API; a request
    missing them (e.g. a forged/replayed call) is rejected. Unset (dev) → accepted."""
    import json as _json

    raw = await request.body()
    if PAYPAL_WEBHOOK_ID:
        required = ("paypal-transmission-id", "paypal-transmission-sig",
                    "paypal-transmission-time", "paypal-cert-url", "paypal-auth-algo")
        if not all(request.headers.get(h) for h in required):
            raise HTTPException(status_code=400, detail="Missing PayPal signature headers")
        if not await _paypal_verify(request.headers, raw):
            raise HTTPException(status_code=400, detail="Invalid webhook signature")

    try:
        payload = _json.loads(raw or b"{}")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event = payload.get("event_type", "event")
    await _pay_event(db, None, f"paypal.{event}", provider="paypal", data={"event": event})
    await db.commit()
    return {"received": True}


async def _paypal_verify(headers, raw: bytes) -> bool:
    """Call PayPal's verify-webhook-signature API. Needs PAYPAL_CLIENT_ID/SECRET +
    PAYPAL_API_BASE; returns False on any error so verification failures never pass."""
    import json as _json
    base = os.getenv("PAYPAL_API_BASE", "https://api-m.paypal.com")
    cid, secret = os.getenv("PAYPAL_CLIENT_ID", ""), os.getenv("PAYPAL_CLIENT_SECRET", "")
    if not (cid and secret):
        return False
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            tok = await client.post(f"{base}/v1/oauth2/token", auth=(cid, secret),
                                    data={"grant_type": "client_credentials"})
            tok.raise_for_status()
            access = tok.json()["access_token"]
            body = {
                "transmission_id":   headers["paypal-transmission-id"],
                "transmission_time": headers["paypal-transmission-time"],
                "cert_url":          headers["paypal-cert-url"],
                "auth_algo":         headers["paypal-auth-algo"],
                "transmission_sig":  headers["paypal-transmission-sig"],
                "webhook_id":        PAYPAL_WEBHOOK_ID,
                "webhook_event":     _json.loads(raw or b"{}"),
            }
            resp = await client.post(f"{base}/v1/notifications/verify-webhook-signature",
                                     headers={"Authorization": f"Bearer {access}"}, json=body)
            resp.raise_for_status()
            return resp.json().get("verification_status") == "SUCCESS"
    except Exception:
        return False
