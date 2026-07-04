# PDFForge — Security & OWASP Top 10 (2021) Coverage

| OWASP | Risk | Controls in PDFForge |
|---|---|---|
| A01 | Broken Access Control | Per-tenant isolation enforced in every query (`_get_doc_or_404` filters by `owner_id`; comments/signatures/folders/projects/keys scoped to user). Verified by `tests/test_increment23.py::TestTenantIsolation`. Relational RBAC (roles/permissions, `/auth/permissions`). |
| A02 | Cryptographic Failures | TLS in transit (Caddy/Ingress + HSTS header). Passwords hashed with bcrypt. Sensitive fields encrypted at rest via `shared/crypto.py` (Fernet, key derived from `SECRET_KEY`) — applied to the MFA secret. JWTs signed with a strong rotated `SECRET_KEY`. |
| A03 | Injection | SQLAlchemy + parameterized `text()` everywhere (no string-built SQL). Pydantic validation on all request bodies. PDF uploads validated by magic bytes + size. |
| A04 | Insecure Design | Service-per-domain, least-privilege headers between services, queue for heavy work, idempotent operations, soft-delete for recoverability. |
| A05 | Security Misconfiguration | Gateway security-headers middleware: CSP, `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, HSTS. CORS is an explicit allowlist (no `*` with credentials). Secrets in `.env` (git-ignored) / k8s Secrets; `.env.example` sanitized. |
| A06 | Vulnerable Components | Pinned dependencies; `npm audit` / `pip-audit` in scope. Known build-time-only `canvas→tar` advisories documented + `tar` pinned via overrides. |
| A07 | Identification & Auth Failures | Email verification, password-reset tokens (short-lived), **account lockout** (Redis, 5 fails → 429), **MFA (TOTP)**, refresh-token rotation + revocation on logout. |
| A08 | Software & Data Integrity | Webhooks signature-verified (Stripe). Version history with restore. Audit logs for sensitive actions. |
| A09 | Logging & Monitoring Failures | `audit_logs` table (user, action, resource, IP, UA). Prometheus metrics + alert rules (`monitoring/alerts.yml`): service down, 5xx rate, p95 latency, 429 spike. |
| A10 | SSRF | No user-controlled outbound URL fetching in document flows; OAuth/token endpoints are fixed provider URLs. S3 access via server-side keys only. |

## Authentication model & CSRF
The API is consumed with `Authorization: Bearer <JWT>` (and `X-API-Key` for automation).
Bearer tokens are **not** automatically attached by browsers cross-site, so the primary API
surface is structurally CSRF-resistant. If cookie-based session auth is enabled for a deployment,
add CSRF tokens (double-submit) + `SameSite=Strict` cookies.

## Rate limiting
Per-IP at the gateway (Redis, default 100/60s). A trusted `RATE_LIMIT_BYPASS_TOKEN` header is
honored only when that env var is set (unset in production → no bypass) — used by CI to run the
full suite without tripping the limiter.

## Known gaps / hardening backlog
- Move browser auth tokens to `HttpOnly` cookies (currently client-stored) — requires CSRF tokens.
- Extend field-level encryption beyond the MFA secret (e.g., OAuth provider IDs).
- Automated SAST/DAST (CodeQL, OWASP ZAP) and dependency scanning gates in CI.
- WAF + per-user (not just per-IP) rate limits at the edge.
