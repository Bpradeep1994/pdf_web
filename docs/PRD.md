# PDFForge — Product Requirements Document

## 1. Overview
PDFForge is a multi-tenant SaaS for viewing, editing, converting, OCR-ing, signing, and
collaborating on PDF documents in the browser. Users upload documents to private storage,
edit them with a rich canvas, run conversions/OCR, request signatures, comment with teammates,
and manage billing — all behind authenticated, rate-limited APIs.

## 2. Goals
- Let any user edit and transform PDFs without desktop software.
- Be secure and multi-tenant (strict per-user isolation).
- Scale horizontally (stateless services, queue-backed heavy work).
- Be self-hostable (Docker Compose) and cloud-deployable (Kubernetes/EKS).

## 3. Personas
- **Individual** — edits, converts, signs their own documents.
- **Team member** — shares, comments, co-reviews within a project.
- **Admin** — manages users, views revenue/subscriptions/audit logs.

## 4. Functional Requirements
| # | Requirement |
|---|---|
| FR-1 | Register/login (email+password), email verification, password reset |
| FR-2 | OAuth login (Google/GitHub/Microsoft) when configured |
| FR-3 | MFA (TOTP), account lockout after repeated failures |
| FR-4 | Upload / list / rename / move / soft-delete PDFs; folders |
| FR-5 | View PDF: zoom, rotate, search, thumbnails, page nav |
| FR-6 | Edit: text (font/size/color, inline), draw, shapes, image (resize/rotate/crop), highlight, redact, watermark |
| FR-7 | Page tools: rotate, duplicate, extract, delete, reorder, replace, merge, split, compress |
| FR-8 | Convert: PDF↔DOCX/XLSX/PPTX, PDF→PNG/JPG/TXT/HTML, image→PDF |
| FR-9 | OCR: text extraction, searchable PDF, table extraction |
| FR-10 | Signatures: draw/upload/type; single + multi-signer requests; audit |
| FR-11 | Collaboration: comments, @mentions, version history/restore, sharing, realtime presence |
| FR-12 | Notifications (in-app + email), unread counts |
| FR-13 | Billing: Stripe checkout, subscriptions, invoices, portal, webhooks |
| FR-14 | Admin: stats, users (role/active), revenue, subscriptions, documents, audit logs |
| FR-15 | API keys for programmatic access |
| FR-16 | RBAC: roles + granular permissions |

## 5. Non-Functional Requirements
| Attribute | Target |
|---|---|
| Availability | 99.9% (HA deployment) |
| Latency | p95 < 300ms for CRUD; heavy ops async via queue |
| Security | OWASP Top-10 controls; per-tenant isolation; encryption in transit + sensitive fields at rest |
| Scalability | Stateless services behind HPA; S3 for blobs; Redis/RabbitMQ for cache/queue |
| Observability | Prometheus metrics + alerts; structured logs; audit trail |
| Recoverability | RPO ≤ 6h (≤5min with RDS PITR), RTO ≤ 1h (see DR_RUNBOOK.md) |
| Maintainability | Service-per-domain, typed APIs, migrations, tests in CI |

## 6. User Stories
- As a user, I can upload a PDF and see it render so I can start editing.
- As a user, I can click on the page and type text inline so editing feels natural.
- As a user, I can convert my PDF to Word/Excel so I can reuse the content.
- As a user, I can request signatures from multiple people and track who has signed.
- As a teammate, I can comment and @mention so reviews happen in-context.
- As a user, I can undo/redo and restore previous versions so mistakes are safe.
- As an admin, I can see revenue and manage users so I can run the business.
- As a developer, I can mint an API key so I can automate document workflows.

## 7. Use Cases (happy paths)
1. **Edit text** — open editor → Text tool → click → type → Enter → version saved.
2. **Convert** — Convert ▾ → DOCX → background converts → download URL returned.
3. **Sign request** — Signatures panel → add signer emails → request created → signer signs field → request completes.
4. **Subscribe** — Billing → checkout → Stripe → webhook activates subscription + records invoice/payment.

## 8. Out of Scope (current)
- Real-time co-editing of the same canvas (presence/comments only).
- Native mobile apps.
- On-prem air-gapped deployment.

See **ARCHITECTURE.md** for system/sequence/data-flow diagrams and **SECURITY.md** for OWASP mapping.
