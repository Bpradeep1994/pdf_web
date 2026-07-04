"""
Transactional email (verification + password reset). Uses SMTP when configured
(SMTP_HOST set) — works with Resend/SES/Gmail SMTP. If not configured, it logs the
link instead of failing (so dev/self-host still works). Send functions are sync and
scheduled via FastAPI BackgroundTasks (run in a threadpool → non-blocking).
"""
import os
import ssl
import smtplib
import logging
from email.message import EmailMessage

log = logging.getLogger("emailer")

SMTP_HOST     = os.getenv("SMTP_HOST", "")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL    = os.getenv("FROM_EMAIL", SMTP_USER or "no-reply@pdfforge.local")
APP_URL       = os.getenv("NEXT_PUBLIC_APP_URL", "http://localhost:3000")
# Treat the .env.example placeholders as "not configured" so dev logs the link
# instead of throwing SMTP auth errors on every signup.
_PLACEHOLDER  = (not SMTP_USER) or ("your@email" in SMTP_USER) or (SMTP_PASSWORD in ("", "your-app-password"))
EMAIL_ENABLED = bool(SMTP_HOST) and not _PLACEHOLDER


def _send(to: str, subject: str, body: str) -> None:
    if not EMAIL_ENABLED:
        log.warning("[email:stub] to=%s | %s | %s", to, subject, body.replace("\n", " "))
        return
    try:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = FROM_EMAIL, to, subject
        msg.set_content(body)
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            s.starttls(context=ssl.create_default_context())
            if SMTP_USER:
                s.login(SMTP_USER, SMTP_PASSWORD)
            s.send_message(msg)
    except Exception as e:  # never break the request path on email failure
        log.error("email send failed to %s: %s", to, e)


def send_verification(to: str, token: str) -> None:
    link = f"{APP_URL}/verify-email?token={token}"
    _send(to, "Verify your PDFForge email", f"Welcome to PDFForge!\n\nVerify your email:\n{link}\n")


def send_password_reset(to: str, token: str) -> None:
    link = f"{APP_URL}/reset-password?token={token}"
    _send(to, "Reset your PDFForge password",
          f"Reset your password:\n{link}\n\nIf you didn't request this, ignore this email.\n")


def send_payment_otp(to: str, code: str) -> None:
    _send(to, "Your PDFForge payment code",
          f"Your one-time payment verification code is: {code}\n\nIt expires in 5 minutes. "
          f"If you didn't start a payment, ignore this email.\n")


# ── SMS (stub) ───────────────────────────────────────────────────────────────
# Real delivery needs an SMS provider (Twilio/MSG91/etc.). With TWILIO_* env set this
# would call the provider; otherwise it logs (dev) so the flow still works.
TWILIO_SID   = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM  = os.getenv("TWILIO_FROM", "")
SMS_ENABLED  = bool(TWILIO_SID and TWILIO_TOKEN and TWILIO_FROM)


def send_sms(to_phone: str, message: str) -> None:
    if not SMS_ENABLED:
        log.warning("[sms:stub] to=%s | %s", to_phone, message)
        return
    try:
        # Twilio REST (no SDK dependency): POST form to the Messages endpoint.
        import base64
        import urllib.request
        import urllib.parse
        url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json"
        data = urllib.parse.urlencode({"From": TWILIO_FROM, "To": to_phone, "Body": message}).encode()
        req = urllib.request.Request(url, data=data)
        auth = base64.b64encode(f"{TWILIO_SID}:{TWILIO_TOKEN}".encode()).decode()
        req.add_header("Authorization", f"Basic {auth}")
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        log.error("sms send failed to %s: %s", to_phone, e)
