# Implementation Progress & Roadmap

## ✅ Increment 26 — Super Admin panel (10 modules)

Full multi-module admin at `/admin` (clean-minimal, left sub-nav, lazy-loaded, charts, inline actions):
- **Dashboard** (KPIs + uploads chart), **Users** (role + activate/deactivate inline),
  **Documents** (all tenants), **Revenue** (totals + by-month chart), **Subscriptions**,
  **Invoices**, **Support Tickets** (status + respond), **Analytics** (signups/docs time-series),
  **Settings** (platform toggles), **Audit Logs**.
- DB migration `0007`: `support_tickets`, `platform_settings`.
- Backend: admin endpoints for every module + user-facing `/support/tickets` (create/list).
  All `/admin/*` are admin-RBAC gated (403 for non-admins — tested).
- Gateway routes `/api/v1/support` → auth service.
- Tests `tests/test_increment25.py` (11): support flow + admin access-control on all 10 endpoints.
  All admin endpoints verified live (stats/users/documents/revenue/subscriptions/invoices/
  support-tickets/analytics/settings/audit-logs + settings PUT).

## ✅ Increment 25 — spec alignment: RBAC, annotations, payments, docs, OWASP, CI

Closes the four gaps found auditing against the 22-step PDFForge spec. Full suite: **303 passed**.

**Database (migration `0006` + `database/seed.sql`):**
- New tables: `roles`, `permissions`, `role_permissions`, `user_roles` (granular RBAC),
  `annotations` (stored markup, JSONB), `payments` (Stripe payment records).
- Seed: 3 roles + 11 permissions + mappings + backfill of existing users → role rows.
- `GET /auth/permissions` returns effective permissions (relational, enum fallback).
- Annotations CRUD API (`/documents/{id}/annotations`), tenant-isolated, JSONB round-trips.
- Stripe webhook now records `payments` on `payment_intent.succeeded|failed`.

**Security hardening (OWASP):**
- Gateway security-headers middleware: CSP, HSTS, `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`.
- Field-level encryption at rest (`shared/crypto.py`, Fernet) applied to the MFA secret,
  legacy-plaintext tolerant.
- `docs/SECURITY.md` maps all OWASP Top-10 → concrete controls.

**Design docs (Step 1):** `docs/PRD.md` (requirements, NFRs, user stories, use cases),
`docs/ARCHITECTURE.md` (system + sequence + data-flow mermaid diagrams, API architecture).

**Coverage / CI:** `ci.yml` now runs the **entire pytest suite in one pass** (writes
`RATE_LIMIT_BYPASS_TOKEN` + applies migrations + seed) and emits Jest coverage artifacts.

**Tests:** `tests/test_increment24.py` — permissions, annotation CRUD + isolation, security headers.

## ✅ Increment 24 — full test coverage + single green run + security audit

**The whole backend/structure suite now runs GREEN in one pass: `294 passed, 0 failed`**
(`python -m pytest tests`). Frontend Jest: 5/5.

- **Rate-limit bypass for tests** — gateway honors `X-RateLimit-Bypass: <RATE_LIMIT_BYPASS_TOKEN>`
  (unset in prod → impossible). `tests/conftest.py` injects it on every request, so all 15 suites
  run together without tripping the per-IP limiter. Prod protection unchanged.
- **New suite `test_increment23.py` (9 tests)** — the high-risk gaps:
  - **Multi-tenant isolation**: user B is denied A's documents, comments, signature requests,
    folders, projects, and API keys (read/edit/delete/list).
  - **Gateway auth**: missing/invalid token → 401; `X-API-Key` path resolves to the user → 200.
  - **Conversion** (pdf→txt + unsupported-format 400) and **OCR** (process + status), previously untested.
- **Stale tests corrected** (caught by the single run): `test_structure` still required the
  **removed AI feature** (ai_service, qdrant, AIChatPanel, ai/page) — updated to the real layout
  (+ now asserts the new editor panels/pages); `test_increment13` used `triangle` as an "invalid"
  shape, but triangle is supported — switched to a genuinely invalid shape.
- **Dead AI infra removed** from `kubernetes/` (deployments, services, hpa, configmap) so a k8s
  deploy can't reference a non-existent `ai-service`/`qdrant`.
- **Security audit** — `npm audit`: 6 findings, all in `canvas → @mapbox/node-pre-gyp → tar`,
  an **optional Node-only** dep of `fabric`/`jsdom` used **only at build time** (browsers use native
  canvas; it is never in the shipped bundle or the running service). Pinned a patched `tar` via
  `overrides`; deliberately did **not** run `audit fix --force` (a major `canvas` bump risks breaking
  `fabric@6` right before launch). Accepted, documented build-time risk.

## ✅ Increment 23 — hardening pass: tests, bug fixes, final polish

**Test suite `tests/test_increment22.py` (12 passing)** — covers comments, signatures
(self-sign + multi-signer completion + double-sign rejection + empty-request 400), watermark,
page tools, version restore, table extraction, folders + rename/move, projects, notifications,
API keys. Run it on its own (per-IP rate limiter).

**3 real bugs caught by the suite and fixed before publish:**
1. **Duplicate page → 500** — `fitz.fullcopy_page` is broken in this PyMuPDF build
   (`'bytes' has no attribute m_internal`); replaced with `insert_pdf` from a second handle.
2. **API-key prefix never displayed** — Settings read `key_prefix`, the API returns `prefix`.
3. **Extract-page button did nothing** — frontend expected `download_url`, but extract returns a
   new document `{id}`; now opens the extracted document for download.

**Polish completed:**
- **Redo** — toolbar Redo backed by a version-restore stack; any new edit (incl. in-canvas edits,
  via PDFViewer `onEdited`) invalidates the redo stack.
- **Image crop** — fabric `clipPath` crop tool in `ImageLayer` (toggle rect → apply).
- **OCR table extraction** — `GET /documents/{id}/tables?page=N` (PyMuPDF `find_tables`) +
  toolbar "Tables" button that downloads CSV.

**Deliberately NOT done — ShadCN migration.** Large cosmetic refactor (re-skinning every
component) with zero functional gain and real regression risk — the opposite of what a
pre-publish hardening pass wants. The UI already uses Tailwind + Radix (what ShadCN is built on);
recommend deferring until after launch, if ever.

## ✅ Increment 21 — wiring built backends into the UI + closing feature gaps

**Backend (built + tested):**
- **Watermark** endpoint `POST /documents/{id}/edit/watermark` (diagonal text, opacity/size/rotate)
  → new version. Tested: 200 + version created.
- **Email delivery** wired (`auth_service/emailer.py`) — verification on register + password-reset
  link via SMTP (Resend/SES/Gmail). Proven live (real SMTP handshake); placeholder creds fall back
  to dev-logging the link so signup never breaks.

**Frontend (built, type-checked, serving 200):**
- **Notifications** — `NotificationBell` in the app header (unread badge, feed, mark-all-read, polls 30s).
- **Folders** — dashboard rail (create + filter by folder).
- **Document rename / move-to-folder / real share link** — dashboard context menu.
- **Page tools** in the editor toolbar — rotate / duplicate / extract / delete current page.
- **Version history** — editor modal listing versions with one-click restore (+ reload-signal so
  toolbar edits re-render the page live).
- **API keys** — Settings tab (create → copy once, revoke) + resend-verification banner.
- **Projects/Teams** — new `/projects` page (list / create / delete) + sidebar nav.

## ✅ Increment 22 — editor depth + collaboration UI (completes Increment 21's open list)

All built, type-checked, Docker-compiled, and serving 200; backends smoke-tested live.
- **Comments panel** (`CommentsPanel.tsx`) — list / add (pin to current page) / resolve / delete.
  *Verified:* create 201, list returns it.
- **Signatures panel** (`SignaturePanel.tsx`) — draw-pad signature, **self-sign** the current page,
  **create multi-signer requests** (one field per email), and **sign fields** with status tracking.
  *Verified:* self-sign 200, request→sign-field flips request to `completed`.
- **Interactive image** (`ImageLayer.tsx`, fabric v6) — upload, drag / resize / rotate with handles,
  then flattened onto the page (new `image` tool in the toolbar).
- **Text font controls** — size + color picker in the editor header (active with the Text tool),
  passed through to `insert_text`/`replace`.
- **Undo** — toolbar button restoring the previous version; **auto-save indicator** in the header
  (every edit persists server-side as a version).

### Still open (truly optional / polish)
- True **redo** stack (undo via version-restore is in; redo would need a forward stack).
- Crop-specific image handle + in-place rich-text editing; ShadCN migration; OCR table extraction.

---

This document tracks the incremental, tested build of the AI-Powered PDF Editor SaaS
against the full product spec. Strategy: **extend and harden the existing microservice
codebase** (gateway + auth/pdf/ai/ocr/conversion services, Postgres, Redis, RabbitMQ,
Qdrant, MinIO/S3, Next.js frontend) in small, independently-tested increments — not a
rewrite. Each increment ships code + tests + notes and is verified against the live stack
before the next begins.

---

## ✅ Increment 1 — Security hardening + Phase 1 completion

**Security**
- **JWT secret** (`shared/security.py`): fail-closed in production/staging if the secret is
  missing, < 32 chars, or a known placeholder; warns (and allows) only in local dev.
- **Upload hardening** (`pdf_service`): real `%PDF-` magic-byte check (not the client MIME),
  size limit (`MAX_UPLOAD_MB`, default 100), reject empty/encrypted/corrupt PDFs — validated
  **before** storing.
- **Conversion IDOR fix** (`conversion_service`): the storage key is now resolved from the DB
  by `document_id` **and `owner_id`**; client-supplied `s3_key` is ignored. Prevents converting
  other users' documents.
- **CORS** (`gateway`): secure-by-default explicit allowlist (`ALLOWED_ORIGINS`, default
  `http://localhost:3000`) instead of `*` + credentials.
- **Auth error handling** (`gateway`): missing/empty/garbage credentials on a protected route
  now return a clean **401** (previously 500).
- **MFA enforcement** (`auth_service`): login requires a valid TOTP code when the account has
  MFA enabled (`mfa_code` on `LoginRequest`).

**Phase 1 features**
- **PDF Split** — `POST /documents/{id}/split` with 1-indexed inclusive page ranges (or every
  page); creates owned child documents.
- **PDF Compress** — `POST /documents/{id}/compress` (PyMuPDF `garbage=4, deflate, clean`),
  saved as a new version.
- **Export** — download via browser-reachable presigned URLs (fixed earlier: `S3_PUBLIC_ENDPOINT`).

**Tests:** `tests/test_increment1.py` — 14 passing (security probes, IDOR, upload validation,
split/compress, conversion-as-owner, admin RBAC).

## ✅ Increment 2 (in progress) — Admin Dashboard backend

- New `auth_service/admin.py`, mounted at `/api/v1/admin`, routed through the gateway.
- **RBAC**: `require_admin` dependency (role must be `admin`) → 401 unauth, 403 non-admin.
- `GET /admin/stats` — aggregated platform metrics (users, documents, AI queries, 7-day deltas,
  30-day uploads chart) via parameterized SQL across the shared database.
- `GET /admin/users` — **paginated** + searchable user list (`page`, `page_size`, `search`).
- `PATCH /admin/users/{id}` — change role / activate-deactivate (self-deactivation guarded).
- Frontend Admin page wired to the paginated response.
- Verified end-to-end (RBAC + stats + users) against the live stack.

---

## ⚠️ Increment 3 — Data-model expansion (REVISED / reverted)

Initial attempt added a `shared/models` package + Alembic with new tables. **This was a
mistake**: the project already has an authoritative SQL schema at
`database/migrations/001_init.sql` (mounted into Postgres init) that defines
`subscriptions`, `invoices`, `usage_quotas`, `signature_requests`, `signature_fields`,
`audit_logs`, `document_comments`, `jobs`, plus a **`create_user_quota` trigger** that
seeds `usage_quotas`/`subscriptions` on every registration. The new models **diverged**
from it, and dropping `usage_quotas` broke registration.

**Resolution:**
- Treat `database/migrations/001_init.sql` as the **single source of truth** for the schema.
- Reset the dev DB to that canonical schema (trigger + all tables restored; registration verified).
- Removed the divergent `shared/domain` package + `alembic/` migration.
- **Lesson:** there is no need for new tables for billing/signatures/audit/comments — they
  already exist canonically. Future feature work builds on those.
- Proper Alembic adoption (baselined from `001_init.sql`) is deferred to the Infra increment.

## ✅ Increment 4 — E-Signature (on the canonical schema)

- `pdf_service/esign.py`, mounted at `/api/v1/signatures` (gateway route added). Uses the
  canonical `signature_requests` / `signature_fields` / `audit_logs` tables via parameterized SQL.
- **Self-sign**: `POST /signatures/apply` — stamp a signature image (base64 PNG) onto your
  own document at a page/coordinate → new document version.
- **Signature requests**: `POST /signatures/requests` (with placed fields per signer),
  `GET /signatures/requests`, `GET /signatures/requests/{id}`,
  `POST /signatures/requests/{id}/sign` (sign a field; when all fields signed → request
  `completed` + final signed version).
- Ownership enforced; every signing action written to **audit_logs** (user, IP, user-agent, ts).
- PDF stamping via PyMuPDF `insert_image`. Frontend `signatureApi` client added.
- **Tests:** `tests/test_increment4.py` — 7 passing (self-sign, ownership 404, invalid input,
  full request→sign→complete flow, auth). Registration regression guard included.

## ✅ Increment 5 — Audit Logs

- Reusable writer `shared/audit.py` (`record(...)`) → canonical `audit_logs` table; never
  breaks the primary request path (best-effort).
- **Event capture** wired across services: `user.register`, `user.login`, `user.logout`
  (auth), `admin.user_updated` (admin), `document.delete`, `document.share` (pdf),
  `signature.applied|requested|signed` (esign) — each with user, IP, user-agent, timestamp.
- **Admin viewer**: `GET /admin/audit-logs` — RBAC admin-only, paginated, filter by
  `action` / `user_id`.
- Frontend `adminApi` client (stats/users/updateUser/auditLogs) added.
- **Tests:** `tests/test_increment5.py` (RBAC) + verified end-to-end that events are captured
  and filterable.

## ✅ Increment 6 — Infra & CI/CD

- **Helm chart** `deploy/helm/pdf-editor`: templates all 7 services (Deployments + Services +
  CPU HPAs), a ConfigMap (cluster service URLs + non-secret config), ALB Ingress
  (api/app hosts), and an Alembic **migrate Job** (pre-install/upgrade hook). Secrets are
  provided out-of-band (documented; no plaintext in the chart). **`helm template` renders
  cleanly** → 7 Deployments, 7 Services, 7 HPAs, ConfigMap, Ingress, Job.
- **GitHub Actions**: `ci.yml` (frontend type-check/lint/build, backend static tests, full
  docker-compose integration run of e2e + increment suites) and `cd.yml` (build/push all 7
  images to GHCR on `v*` tag → `helm upgrade --install` to EKS).
- **Alembic** (SQL-first adoption): `backend/alembic/` with async env + `0001_baseline`
  marker; baseline schema stays in `database/migrations/001_init.sql`, incremental changes
  via revisions. **Validated** against the live DB (`stamp` → `current` → `upgrade head` OK).
- **AWS deployment guide**: `docs/DEPLOYMENT.md` (EKS, RDS, ElastiCache, Amazon MQ, S3,
  CloudFront, Route53, secrets, Helm, CI/CD, ops).

## ✅ Increment 7 — Frontend depth + SEO

- **Landing page** (`app/page.tsx`): hero, feature grid, CTA, footer; SEO metadata +
  OpenGraph; dark-mode aware. Replaces the old redirect-only root.
- **Public pricing page** (`app/pricing/page.tsx`) with SEO metadata.
- **Dark mode**: `ThemeToggle` (next-themes, Tailwind `darkMode: class`).
- **Admin Audit tab**: wired to `/admin/audit-logs` (Increment 5) — time/action/resource/user/IP.
- **SEO**: `robots.ts` + `sitemap.ts` → `/robots.txt` and `/sitemap.xml` (private routes disallowed).
- Verified: type-check + lint clean, frontend build OK, landing/pricing/robots/sitemap all serve 200.

## ✅ Increment 8 — AI / RAG layer

- **RAG pipeline**: chunk → embed → Qdrant upsert → vector retrieve → context injection →
  cited answer (sources returned with page + score).
- **Multi-provider** LLM abstraction: OpenAI, Anthropic, **Gemini** (new) — selected via
  `LLM_PROVIDER`; key-gated with graceful stub fallback.
- **Deterministic stub embeddings** (hash-seeded) so RAG retrieval is meaningful offline /
  without API keys (demo + tests) — activates real embeddings when `OPENAI_API_KEY` is set.
- Endpoints: `/ai/chat` (RAG), `/ai/summarize`, `/ai/translate`, `/ai/analyze`
  (contract | invoice | resume | **requirements** | general), `/ai/index`, `/ai/sessions`.
- docker-compose passes `GEMINI_API_KEY` / `LLM_PROVIDER` / model envs through.
- **Tests:** `tests/test_increment8.py` — 11 passing (chat, session continuity, summarize,
  translate, all analyze types, auth). Real provider output activates with keys.

## ✅ Increment 9 — OAuth + User management + WSL stability

- **OAuth** (Google / GitHub / **Microsoft**): `GET /auth/oauth/{provider}` initiation
  (302 to provider, or **503 if not configured** — no more 404s), `GET /auth/oauth/{provider}/callback`
  (exchanges code → upserts user → redirects SPA with tokens), plus the SPA `POST /auth/oauth/callback`.
  Frontend `/(auth)/oauth/callback` page stores tokens. Key-gated; activates on client IDs.
- **User management**: `PATCH /auth/me` (profile) and `POST /auth/change-password`
  (verifies current, rotates password, revokes refresh tokens, audited) — fixes the previously
  broken Settings page.
- **Infra/stability**: root cause of the recurring Docker crashes found — host has only **5.9 GB RAM**.
  Added `~/.wslconfig` (memory=4GB, swap=8GB on D:, autoMemoryReclaim) so containers swap instead
  of OOM-killing. Verified: WSL now 3.9 GB RAM + 8 GB swap; full 12-container stack stable.
- **Tests:** `tests/test_increment9.py` — 7 passing (profile, password flow + wrong-current,
  OAuth unsupported 400, providers 503-when-unconfigured). Regression: inc1/4/5/8 all green.

## ✅ Increment 10 — AI feature removed (per request)

AI returned only stub output without LLM keys, so the feature was removed from the app:
- **Frontend**: deleted `/ai` page + `AIChatPanel`, removed the "AI Chat" nav item, the editor
  "AI Assistant" panel, `aiApi`, and all AI marketing copy/cards on the landing page.
- **Gateway**: removed the `/api/v1/ai` route.
- **docker-compose**: removed `ai_service` and `qdrant` (and its volume) — also frees RAM on the
  5.9 GB host (now 10 containers, was 12).
- **CI/CD + Helm**: removed `ai_service` from the build matrix, Helm services, configmap, and
  secret keys.
- **Tests**: deleted `test_increment8.py` and the AI cases from `test_e2e_api.py`.
- The `backend/ai_service/` source is retained (unwired) so AI can be re-enabled later with keys.
- Verified: `/api/v1/ai` → 404, `/ai` page → 404; e2e 35 + inc1/4/5/9 all green.

## ✅ Increment 11 — Billing (Stripe)

- `auth_service/billing.py`, mounted at `/api/v1/billing` (gateway route added; webhook is a
  **public, signature-verified** path). Uses the canonical `subscriptions`/`invoices` tables.
- Endpoints: `GET /plans`, `GET /subscription` (seeded `free` on signup), `GET /invoices`,
  `POST /checkout` (Stripe Checkout session), `POST /portal` (billing portal),
  `POST /webhook` (syncs subscription plan/status + records invoices on Stripe events).
- **Feature-flagged**: read endpoints always work; actions return **503 when unconfigured**.
  A Stripe **test key is present** in this env, so billing is live — to enable purchases add
  `STRIPE_PRICE_PRO` / `STRIPE_PRICE_BUSINESS` (price IDs) + `STRIPE_WEBHOOK_SECRET`.
- Frontend `billingApi` + billing page wired to `checkout → redirect` (graceful 503 toast).
- **Tests:** `tests/test_increment11.py` — 8 passing (plans, seeded subscription, invoices,
  auth, mode-aware checkout/webhook). Regressions inc1/5/9 green.

## ✅ Increment 12 — Projects / Team Workspaces + Notifications

- **Schema**: Alembic `0002` adds `projects`, `project_members`, `project_documents`,
  `notifications` (on top of `0001_baseline`). Applied & verified.
- **Projects/Teams** (`pdf_service/projects.py`, `/api/v1/projects`): create/list/get/delete
  projects; add/remove **members with roles** (owner | editor | viewer); add/remove documents.
  Membership is the access boundary (non-members get 404; viewers can't delete → 403).
- **Notifications** (`auth_service/notifications.py`, `/api/v1/notifications`): list (+unread
  filter), unread-count, mark-read, mark-all-read. Reusable writer `shared/notify.py`; wired so
  adding a project member generates a `project.invited` notification for them.
- Frontend `projectsApi` + `notificationsApi` clients added (UI wiring is future work).
- **Tests:** `tests/test_increment12.py` — 6 passing (project CRUD, member RBAC, notification
  on member-add, mark-read, auth).

> Test note: running *all* suites back-to-back can trip the gateway rate limit (100/60s per IP)
> and cause false failures — run suites in groups, or raise `RATE_LIMIT_REQUESTS` for CI.

## ✅ Increment 13 — Real-time collaboration + Enterprise API keys + editor depth

- **Real-time collaboration** (Phase 4 #19): gateway `WS /ws/documents/{doc_id}` with a
  Redis pub/sub `RoomManager` (scales across replicas). Token via query param; presence
  join/leave + message broadcast (cursors/live edits) stamped with sender. **Verified** with a
  2-client test (broadcast + bad-token rejection).
- **Enterprise API keys** (Phase 4 #21): `api_keys` table (Alembic 0003); `/api/v1/keys`
  create/list/revoke (raw key shown once, SHA-256 stored); gateway resolves `X-API-Key` →
  user via `/internal/validate-key`, so every API works programmatically.
- **Editor depth**: `/documents/{id}/edit/shape` (rect/line/ellipse/circle) and `/edit/image`
  (insert base64 image) via PyMuPDF → new version. Undo/redo = existing version restore;
  autosave = immediate versioning. Frontend `keysApi` + `documentsApi.addShape/addImage`.
- **Tests:** `tests/test_increment13.py` — 6 passing (API key create/use/revoke, bad key,
  shapes, image) + WS verified via container script.

## ✅ Increment 14 — PDFForge gap-fill (folders, page tools, comments)

Verified the build against the "PDFForge" plan and filled the real backend gaps:
- **Folders** (Alembic 0004: `folders` + `documents.folder_id`): nestable folders CRUD
  (`/api/v1/folders`), list folder documents.
- **Document rename / move**: `PATCH /api/v1/documents/{id}` (original_name and/or folder_id,
  with target-folder ownership check).
- **Page tools** (`/documents/{id}/pages/...`): rotate, delete, reorder, duplicate, and
  **extract** (→ new document) via PyMuPDF (new version on in-place ops).
- **Comments + @mentions** (`/documents/{id}/comments`, canonical `document_comments`):
  threaded create/list/update(resolve)/delete; mentions generate notifications.
- Frontend clients added: `foldersApi`, page-tool + comment methods on `documentsApi`.
- **Tests:** `tests/test_increment14.py` — 7 passing.

## ✅ Increment 15 — small backend gap-fill

- **Email verification**: register issues an `email_verify` token; `POST /auth/verify-email`
  consumes it (→ `is_verified=true`); `POST /auth/resend-verification` (returns the token in dev
  for testability; Resend delivery wired for prod). Tested.
- **Replace pages**: `POST /documents/{id}/pages/replace` (swap a page with a page from another
  owned document) via PyMuPDF → new version. Tested.
- **Admin storage analytics**: `/admin/stats` now returns `storage_bytes` (documents + versions).
  Verified.
- **Tests:** `tests/test_increment15.py` — 4 passing.

## ✅ Increment 16 — Viewer: thumbnail panel + text search (Phase 3)

- **Thumbnail rail** (`PDFViewer`): collapsible left panel rendering every page (via the
  existing render endpoint at low zoom), click-to-navigate, current page highlighted.
- **Text search**: search box → fetches page text (`/documents/{id}/text`), lists matching
  pages with snippets, jumps to the first/selected match.
- Reuses existing backend endpoints (no PDF.js client rewrite needed); editing overlay preserved.
- Verified: type-check + lint clean, frontend builds and serves 200.

## ✅ Increment 17 — fabric.js freehand drawing canvas (Phase 4 editor)

- `DrawLayer.tsx` (fabric.js, dynamically imported to avoid SSR): an interactive overlay on the
  page with **Pen** (thin opaque) and **Marker** (thick translucent) brushes, colour palette,
  **undo / clear**, and **Apply / Cancel**.
- "Draw" tool added to the editor Toolbar; PDFViewer mounts the canvas sized to the page image.
- On **Apply**, the strokes export to a transparent PNG and flatten onto the PDF via the
  existing `/edit/image` endpoint (px→pts scaling), producing a new version.
- Type-check + lint clean; frontend builds and serves with fabric.js included.

## ✅ Increment 18 — vector shapes + frontend test tooling

- **Vector shapes**: `/edit/shape` extended to **arrow** (line + computed arrowhead),
  **triangle**, and **polygon** (`points[]`) via PyMuPDF — alongside rect/line/ellipse/circle.
- **Jest** (unit): `jest.config.js` (next/jest), `jest.setup.js`, `src/__tests__/utils.test.ts`
  → **5/5 passing** (`npm test`).
- **Playwright** (E2E): `playwright.config.ts` + `e2e/smoke.spec.ts` — **4/4 passing in real
  Chromium** (landing/pricing/login render + full register→dashboard happy path) against the live
  stack. `tests/test_increment18.py` covers the shapes (4 passing).
- CI (`ci.yml`) extended with frontend **jest** + **playwright** jobs.

## ✅ Increment 19 — production-readiness hardening (key-free launch blockers)

- **Account lockout / brute-force protection**: Redis-backed per-account failed-login counter
  (`LOGIN_MAX_ATTEMPTS`/`LOGIN_LOCKOUT_WINDOW`) → 429 after N failures; fail-open if Redis down.
- **Soft deletes**: `documents.deleted_at` (Alembic 0005); delete is now soft, `_get_doc_or_404`
  + listing exclude deleted → recoverable. (Tested: delete→204, then 404 + hidden.)
- **Monitoring**: gateway exposes Prometheus `/metrics` (prometheus-fastapi-instrumentator);
  `monitoring/prometheus.yml` + `monitoring/alerts.yml` (down / 5xx / p95 latency / 429 spike).
- **Disaster recovery**: `backend/scripts/{backup,restore}.sh` (pg_dump + S3) and
  `docs/DR_RUNBOOK.md` (RTO ≤ 1h / RPO targets, failure playbook, drill cadence).
- **Secrets hygiene**: `.gitignore` (excludes `.env`), rotated live `SECRET_KEY` to a strong
  64-char value, sanitized + corrected `.env.example`.
- **Tests:** `tests/test_increment19.py` — 3 passing (lockout, soft delete, /metrics);
  inc1 regression 14/14 green.

## ✅ Increment 20 — self-hosted launch path (no cloud account)

Brought the cloud-gated items to a **single-VM / local** footing — no AWS needed (MinIO=S3,
local PG/Redis/RabbitMQ):
- **TLS**: Caddy reverse-proxy as a compose `tls` profile (`deploy/caddy/Caddyfile`) — self-signed
  `https://localhost` locally, **auto Let's Encrypt** for a real domain. No manual certs.
- **Monitoring**: Prometheus + Grafana as a `monitoring` profile. **Verified**: Prometheus scrapes
  the gateway target (`health=up`). Grafana datasource provisioned.
- **Real load test**: k6 (`tests/load/smoke.js`) — **723 req/s, p95 127ms, 0% errors** at 50 VUs
  on the 5.9 GB dev box (both thresholds passed). Converts "performance unmeasured" → real baseline.
- **Self-hosted guide**: `docs/SELF_HOSTED.md` (one VM + Caddy auto-TLS + monitoring + cron backups;
  prod checklist + hardware guidance).

### Still requiring infra you don't have yet (not code — ops choices)
- True **HA / multi-AZ failover** (needs ≥2 nodes or managed DB); single VM = single point of failure.
- **High-scale** load/stress (10k+) needs bigger hardware than the dev box.
- **Activate** OAuth (provider keys) + Stripe (price IDs + live webhook) when you have them.
- **Drill** the DR restore once on your target host. · Cosmetic: ShadCN migration.

## Remaining roadmap (mapped to the spec deliverables)

| Increment | Scope | External deps |
|---|---|---|
| 3 | **Data model expansion + Alembic** — Projects, Annotations, Comments, Signatures, Subscriptions, Invoices, Notifications, AuditLogs tables + migrations + ER diagram | none |
| 4 | **E-Signature** (draw/upload/type, multi-signer, audit trail, timestamping) | none |
| 5 | **Audit Logs** (event capture across services → `audit_logs`, admin viewer) | none |
| 6 | **OAuth** (Google/GitHub/Microsoft initiation + callback) | provider client IDs/secrets |
| 7 | **Billing** (Stripe checkout, webhooks, plans, invoices, entitlements) | Stripe keys |
| 8 | **AI/RAG done properly** (OpenAI/Anthropic/Gemini providers, chunk→embed→Qdrant→retrieve→cite, contract/invoice/resume analysis) | LLM API keys |
| 9 | **Real-time collaboration** (WebSocket service, presence, conflict resolution) + **Team Workspaces** | none |
| 10 | **Infra** (Alembic in CI, Kubernetes manifests, Helm charts, GitHub Actions, AWS EKS/RDS/S3/CloudFront guide) | AWS account for deploy |
| 11 | **Editor depth** (image insert/resize/rotate, draw, shapes, underline, undo/redo, autosave) | none |
| 12 | **Frontend** (landing, pricing, dark mode, a11y, SEO) | none |

**Notes / decisions**
- Increments 6, 7, 8 need real credentials (OAuth apps, Stripe, LLM keys). They can be built
  against test/sandbox keys; provide keys when ready or they ship in a disabled/stub state.
- All services share one Postgres database, so cross-domain reads (e.g. admin stats) use
  parameterized SQL rather than cross-service model imports.
