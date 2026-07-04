# PDFForge — Architecture

## 1. System Architecture

```mermaid
flowchart TB
  subgraph Client
    FE[Next.js Frontend<br/>PDF.js + Fabric.js]
  end
  subgraph Edge
    CADDY[Caddy / Ingress<br/>TLS termination]
  end
  GW[API Gateway<br/>FastAPI · auth resolve · rate limit · security headers]
  AUTH[Auth Service<br/>users, OAuth, MFA, RBAC, billing, admin, notifications, keys]
  PDF[PDF Service<br/>edit, tools, pages, comments, annotations, signatures, projects, folders]
  OCR[OCR Service<br/>Tesseract/PaddleOCR]
  CONV[Conversion Service<br/>pdf2docx, openpyxl, python-pptx, LibreOffice]
  PG[(PostgreSQL)]
  REDIS[(Redis)]
  MQ[(RabbitMQ)]
  S3[(S3 / MinIO)]
  PROM[Prometheus + Grafana]

  FE --> CADDY --> GW
  GW --> AUTH & PDF & OCR & CONV
  AUTH --> PG & REDIS
  PDF --> PG & S3 & MQ
  OCR --> S3
  CONV --> S3
  GW -. /metrics .-> PROM
  GW <-->|WebSocket pub/sub| REDIS
```

## 2. Service responsibilities
- **Gateway** — single entry; resolves JWT / cookie / `X-API-Key` → injects `x-user-*` headers; per-IP rate limit (Redis); security headers; Prometheus `/metrics`; WebSocket fan-out via Redis pub/sub.
- **Auth** — register/login/refresh/reset/verify, OAuth, MFA, RBAC (`/permissions`), admin, billing (Stripe), notifications, API keys.
- **PDF** — documents CRUD, edits (text/draw/shape/image/highlight/redact/watermark), page tools, versions, comments, annotations, signatures, projects, folders, tables.
- **OCR** — image→text, searchable PDF.
- **Conversion** — PDF↔Office, PDF→image/text, office→PDF.

## 3. Sequence — authenticated request
```mermaid
sequenceDiagram
  participant FE as Frontend
  participant GW as Gateway
  participant AU as Auth (/internal/validate)
  participant SV as Target Service
  FE->>GW: Request + Bearer JWT
  GW->>GW: rate_limit (Redis)
  GW->>AU: validate token
  AU-->>GW: {user_id, role, valid}
  GW->>SV: proxy + x-user-id/role headers
  SV-->>GW: JSON
  GW-->>FE: JSON (+ security headers)
```

## 4. Sequence — PDF conversion
```mermaid
sequenceDiagram
  participant FE as Frontend
  participant GW as Gateway
  participant CV as Conversion
  participant S3 as S3/MinIO
  FE->>GW: POST /convert/convert {document_id, target}
  GW->>CV: proxy
  CV->>S3: download source by owner-scoped key
  CV->>CV: pdf2docx / openpyxl / python-pptx / fitz
  CV->>S3: upload output
  CV-->>FE: { download_url (presigned) }
```

## 5. Sequence — multi-signer signature
```mermaid
sequenceDiagram
  participant O as Owner
  participant PDF as PDF Service
  O->>PDF: POST /signatures/requests {fields per signer}
  loop each field
    O->>PDF: POST /requests/{id}/sign {field_id, signature}
    PDF->>PDF: stamp image → new version + audit
  end
  PDF->>PDF: all signed → status=completed
```

## 6. Data Flow — upload & edit
```mermaid
flowchart LR
  U[User] -->|upload| GW --> PDF
  PDF -->|validate magic bytes/size| PDF
  PDF -->|put object| S3
  PDF -->|row| PG
  U -->|edit op| PDF -->|new version| S3
  PDF -->|version row + audit| PG
```

## 7. API Architecture
- REST under `/api/v1/*`, routed by prefix in the gateway `SERVICE_MAP`.
- Auth via `Authorization: Bearer`, cookie fallback, or `X-API-Key`.
- Heavy/long work is idempotent and returns presigned URLs; queue (RabbitMQ) for async jobs.
- OpenAPI/Swagger per service at `/docs`.
- Realtime: `/ws/documents/{id}` (gateway) backed by Redis pub/sub.

## 8. Infrastructure
- **Local/self-host:** Docker Compose (+ `tls` and `monitoring` profiles). See SELF_HOSTED.md.
- **Cloud:** Kubernetes manifests in `kubernetes/` (Deployments/Services/Ingress/HPA/Secrets/ConfigMap) for EKS; managed Postgres (RDS), Redis (ElastiCache), RabbitMQ (Amazon MQ), S3, CloudFront.
- **CI/CD:** GitHub Actions (`.github/workflows/ci.yml`, `cd.yml`).
