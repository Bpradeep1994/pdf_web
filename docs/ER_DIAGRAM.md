# Entity-Relationship Diagram

**Authoritative schema:** `database/migrations/001_init.sql` (applied to Postgres on init).
This diagram reflects that canonical schema. A `create_user_quota` trigger seeds a
`usage_quotas` and `subscriptions` row whenever a `users` row is inserted.

```mermaid
erDiagram
    users ||--o{ user_tokens : has
    users ||--o{ refresh_tokens : has
    users ||--|| subscriptions : has
    users ||--|| usage_quotas : has
    users ||--o{ invoices : billed
    users ||--o{ documents : owns
    users ||--o{ jobs : runs
    users ||--o{ ai_sessions : owns
    users ||--o{ audit_logs : acts

    documents ||--o{ document_versions : versioned_by
    documents ||--o{ document_shares : shared_via
    documents ||--o{ document_comments : commented_on
    documents ||--o{ jobs : processed_by
    documents ||--o{ ai_sessions : context_of
    documents ||--o{ signature_requests : signed_via

    document_comments ||--o{ document_comments : replies
    ai_sessions ||--o{ ai_messages : contains
    signature_requests ||--o{ signature_fields : has_fields

    users {
        uuid id PK
        string email UK
        string hashed_password
        user_role role "free|pro|business|enterprise|admin"
        auth_provider auth_provider
        bool is_active
        bool mfa_enabled
        string mfa_secret
    }
    subscriptions {
        uuid id PK
        uuid user_id FK,UK
        string stripe_customer_id UK
        string stripe_subscription_id UK
        user_role plan
        plan_interval interval
        subscription_status status
        timestamptz current_period_end
    }
    invoices {
        uuid id PK
        uuid user_id FK
        string stripe_invoice_id UK
        int amount_paid
        string currency
        string status
        text invoice_url
    }
    usage_quotas {
        uuid id PK
        uuid user_id FK,UK
        int docs_uploaded
        int pages_processed
        int ai_queries
        bigint storage_bytes
        timestamptz reset_at
    }
    documents {
        uuid id PK
        uuid owner_id FK
        string original_name
        text s3_key
        bigint file_size
        int page_count
        doc_status status
        bool is_ocr_done
        bool is_ai_indexed
        jsonb metadata
    }
    document_versions {
        uuid id PK
        uuid document_id FK
        int version
        text s3_key
        uuid created_by FK
    }
    document_shares {
        uuid id PK
        uuid document_id FK
        uuid shared_with FK
        string share_token UK
        string permission
        timestamptz expires_at
    }
    document_comments {
        uuid id PK
        uuid document_id FK
        uuid user_id FK
        uuid parent_id FK
        int page_number
        float x
        float y
        text content
        bool resolved
    }
    jobs {
        uuid id PK
        uuid user_id FK
        uuid document_id FK
        job_type job_type "ocr|ai_index|conversion|thumbnail|signature"
        job_status status "pending|processing|completed|failed"
        jsonb payload
        jsonb result
    }
    ai_sessions {
        uuid id PK
        uuid user_id FK
        uuid document_id FK
        string title
    }
    ai_messages {
        uuid id PK
        uuid session_id FK
        string role
        text content
        int tokens
    }
    signature_requests {
        uuid id PK
        uuid document_id FK
        uuid requester_id FK
        string title
        string status "pending|completed|expired"
        timestamptz completed_at
        text signed_doc_key
    }
    signature_fields {
        uuid id PK
        uuid request_id FK
        string signer_email
        int page_number
        float x
        float y
        float width
        float height
        string field_type "signature|initials|date|text"
        timestamptz signed_at
        text signature "base64"
    }
    audit_logs {
        uuid id PK
        uuid user_id FK
        string action
        string resource
        uuid resource_id
        jsonb metadata
        inet ip_address
        text user_agent
    }
```

## Schema management

The schema is currently created by `database/migrations/001_init.sql` on first DB init
(idempotent enums/tables/triggers). Per-service SQLAlchemy models in each
`*/models.py` map a subset of these tables for ORM use. Converging all schema changes onto
Alembic (baselined from `001_init.sql`) is tracked as Infra-increment work.
```
