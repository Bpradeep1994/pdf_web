# Payments — how upgrades reach your bank (India / Razorpay)

When a user upgrades to Pro/Business, the money flows:

```
  User pays (card / UPI / netbanking)
        │
        ▼
  Razorpay   ← holds funds, deducts ~2% fee
        │  ← settles on a payout schedule (first ~T+3 days, then rolling)
        ▼
  YOUR Indian bank account
```

Your app **activates the plan**; **Razorpay moves the money**. Both are already wired.

## One-time setup

### 1. Create + verify a Razorpay account
- Sign up at https://razorpay.com → complete **KYC**: PAN, business/individual details,
  and **link the bank account** where you want payouts. (You cannot receive money until KYC clears.)

### 2. Get your keys
Dashboard → **Settings → API Keys → Generate Key**. You get:
- `Key Id`  (starts with `rzp_live_…`, public)
- `Key Secret` (private — treat like a password)

### 3. Add a webhook
Dashboard → **Settings → Webhooks → Add New Webhook**:
- URL: `https://api.yourdomain.com/api/v1/billing/webhook/razorpay`
- Secret: choose a strong string (this is `RAZORPAY_WEBHOOK_SECRET`)
- Events: `payment.captured`, `payment.failed`, `order.paid`

### 4. Put it in `.env.production`
```
RAZORPAY_KEY_ID=rzp_live_xxxxxxxx
RAZORPAY_KEY_SECRET=your_key_secret
RAZORPAY_WEBHOOK_SECRET=your_webhook_secret
RAZORPAY_CURRENCY=INR
RAZORPAY_PRICE_PRO=29900        # ₹299 / month (in paise)
RAZORPAY_PRICE_BUSINESS=99900   # ₹999 / month
```
Restart auth_service. The checkout page automatically switches from "Demo mode" to the
real **Razorpay** widget (it reads `razorpay_enabled` from `/api/v1/billing/providers`).

## How it works in the app (already built)

1. User clicks **Upgrade** → `POST /billing/razorpay/order` creates a Razorpay Order.
2. The Razorpay Checkout widget opens → user pays with card / UPI / netbanking.
3. Razorpay returns `payment_id` + `signature` → `POST /billing/razorpay/verify`
   verifies the signature (HMAC-SHA256) and flips the user to their new plan.
4. `POST /billing/webhook/razorpay` is the server-to-server backup confirmation.
5. Razorpay credits your account balance → auto-settles to your bank.

## Testing before going live

Use Razorpay **Test Mode** keys (`rzp_test_…`) first. Test payment methods:
- Card: `4111 1111 1111 1111`, any future expiry, any CVV
- UPI: `success@razorpay`
No real money moves in test mode. Switch to `rzp_live_…` keys when ready.

## Fees, timing, taxes
- **Fee:** ~2% per transaction (Razorpay's standard India rate; confirm in your dashboard).
- **Payout:** first settlement ~3 working days after your first payment; then rolling (daily/weekly per your settings).
- **GST/tax:** you're responsible for tax on your revenue — keep the invoices the app records.

## If you also want non-India customers
Razorpay is India-focused. To charge international cards, add **Stripe** as well
(`STRIPE_SECRET_KEY` + `STRIPE_PRICE_*` + webhook) — the Stripe path is already built.

## Production note (CSP)
If you put a Content-Security-Policy in front of the app (Caddy/Cloudflare), allow the
Razorpay widget:
```
script-src  ... https://checkout.razorpay.com;
frame-src   ... https://api.razorpay.com https://checkout.razorpay.com;
connect-src ... https://api.razorpay.com https://lumberjack.razorpay.com;
```
(The app itself sets no CSP, so no change is needed unless you add one.)
