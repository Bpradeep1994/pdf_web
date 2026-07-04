-- ──────────────────────────────────────────────
-- Extensions
-- ──────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ──────────────────────────────────────────────
-- Enums
-- ──────────────────────────────────────────────
CREATE TYPE user_role AS ENUM ('free', 'pro', 'business', 'enterprise', 'admin');
CREATE TYPE auth_provider AS ENUM ('email', 'google', 'github', 'microsoft');
CREATE TYPE doc_status AS ENUM ('uploading', 'processing', 'ready', 'error');
CREATE TYPE job_status AS ENUM ('pending', 'processing', 'completed', 'failed');
CREATE TYPE job_type AS ENUM ('ocr', 'ai_index', 'conversion', 'thumbnail', 'signature');
CREATE TYPE conversion_format AS ENUM ('pdf', 'docx', 'xlsx', 'pptx', 'png', 'jpg', 'txt');
CREATE TYPE plan_interval AS ENUM ('monthly', 'yearly');
CREATE TYPE subscription_status AS ENUM ('active', 'cancelled', 'past_due', 'trialing');

-- ──────────────────────────────────────────────
-- Users
-- ──────────────────────────────────────────────
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255),
    full_name       VARCHAR(255),
    avatar_url      TEXT,
    role            user_role NOT NULL DEFAULT 'free',
    auth_provider   auth_provider NOT NULL DEFAULT 'email',
    provider_id     VARCHAR(255),
    is_verified     BOOLEAN NOT NULL DEFAULT FALSE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    mfa_enabled     BOOLEAN NOT NULL DEFAULT FALSE,
    mfa_secret      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at   TIMESTAMPTZ
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_provider ON users(auth_provider, provider_id);

-- ──────────────────────────────────────────────
-- Email Verification & Password Reset Tokens
-- ──────────────────────────────────────────────
CREATE TABLE user_tokens (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token      VARCHAR(255) UNIQUE NOT NULL,
    token_type VARCHAR(50) NOT NULL,   -- 'email_verify' | 'password_reset'
    expires_at TIMESTAMPTZ NOT NULL,
    used_at    TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_user_tokens_token ON user_tokens(token);

-- ──────────────────────────────────────────────
-- Refresh Tokens
-- ──────────────────────────────────────────────
CREATE TABLE refresh_tokens (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) UNIQUE NOT NULL,
    device     VARCHAR(255),
    ip_address INET,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ──────────────────────────────────────────────
-- Subscriptions & Billing
-- ──────────────────────────────────────────────
CREATE TABLE subscriptions (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id              UUID UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    stripe_customer_id   VARCHAR(255) UNIQUE,
    stripe_subscription_id VARCHAR(255) UNIQUE,
    plan                 user_role NOT NULL DEFAULT 'free',
    interval             plan_interval,
    status               subscription_status NOT NULL DEFAULT 'active',
    current_period_start TIMESTAMPTZ,
    current_period_end   TIMESTAMPTZ,
    trial_end            TIMESTAMPTZ,
    cancelled_at         TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE invoices (
    id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id            UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    stripe_invoice_id  VARCHAR(255) UNIQUE,
    amount_paid        INTEGER NOT NULL DEFAULT 0,  -- cents
    currency           VARCHAR(3) NOT NULL DEFAULT 'usd',
    status             VARCHAR(50) NOT NULL,
    invoice_url        TEXT,
    invoice_pdf        TEXT,
    period_start       TIMESTAMPTZ,
    period_end         TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ──────────────────────────────────────────────
-- Usage Quotas
-- ──────────────────────────────────────────────
CREATE TABLE usage_quotas (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    docs_uploaded       INTEGER NOT NULL DEFAULT 0,
    pages_processed     INTEGER NOT NULL DEFAULT 0,
    ai_queries          INTEGER NOT NULL DEFAULT 0,
    storage_bytes       BIGINT NOT NULL DEFAULT 0,
    reset_at            TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '1 month'),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ──────────────────────────────────────────────
-- Documents
-- ──────────────────────────────────────────────
CREATE TABLE documents (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename      VARCHAR(500) NOT NULL,
    original_name VARCHAR(500) NOT NULL,
    s3_key        TEXT NOT NULL,
    thumbnail_key TEXT,
    file_size     BIGINT NOT NULL DEFAULT 0,
    page_count    INTEGER,
    mime_type     VARCHAR(100) NOT NULL DEFAULT 'application/pdf',
    status        doc_status NOT NULL DEFAULT 'uploading',
    is_ocr_done   BOOLEAN NOT NULL DEFAULT FALSE,
    is_ai_indexed BOOLEAN NOT NULL DEFAULT FALSE,
    metadata      JSONB NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_documents_owner ON documents(owner_id);
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_documents_created ON documents(created_at DESC);

-- ──────────────────────────────────────────────
-- Document Versions
-- ──────────────────────────────────────────────
CREATE TABLE document_versions (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    version     INTEGER NOT NULL,
    s3_key      TEXT NOT NULL,
    file_size   BIGINT NOT NULL DEFAULT 0,
    comment     TEXT,
    created_by  UUID NOT NULL REFERENCES users(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(document_id, version)
);

-- ──────────────────────────────────────────────
-- Document Shares / Collaboration
-- ──────────────────────────────────────────────
CREATE TABLE document_shares (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    shared_with UUID REFERENCES users(id) ON DELETE CASCADE,
    share_token VARCHAR(255) UNIQUE,          -- for public links
    permission  VARCHAR(20) NOT NULL DEFAULT 'view',  -- view | comment | edit
    expires_at  TIMESTAMPTZ,
    created_by  UUID NOT NULL REFERENCES users(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_shares_document ON document_shares(document_id);
CREATE INDEX idx_shares_token ON document_shares(share_token);

-- ──────────────────────────────────────────────
-- Comments
-- ──────────────────────────────────────────────
CREATE TABLE document_comments (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    parent_id   UUID REFERENCES document_comments(id) ON DELETE CASCADE,
    page_number INTEGER,
    x           FLOAT,
    y           FLOAT,
    content     TEXT NOT NULL,
    resolved    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ──────────────────────────────────────────────
-- Background Jobs
-- ──────────────────────────────────────────────
CREATE TABLE jobs (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    job_type    job_type NOT NULL,
    status      job_status NOT NULL DEFAULT 'pending',
    payload     JSONB NOT NULL DEFAULT '{}',
    result      JSONB,
    error       TEXT,
    started_at  TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_jobs_user ON jobs(user_id);
CREATE INDEX idx_jobs_document ON jobs(document_id);
CREATE INDEX idx_jobs_status ON jobs(status);

-- ──────────────────────────────────────────────
-- AI Chat Sessions
-- ──────────────────────────────────────────────
CREATE TABLE ai_sessions (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    title       VARCHAR(255),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE ai_messages (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES ai_sessions(id) ON DELETE CASCADE,
    role       VARCHAR(20) NOT NULL,  -- user | assistant
    content    TEXT NOT NULL,
    tokens     INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ai_messages_session ON ai_messages(session_id);

-- ──────────────────────────────────────────────
-- E-Signatures
-- ──────────────────────────────────────────────
CREATE TABLE signature_requests (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id    UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    requester_id   UUID NOT NULL REFERENCES users(id),
    title          VARCHAR(255),
    message        TEXT,
    status         VARCHAR(50) NOT NULL DEFAULT 'pending',  -- pending | completed | expired
    expires_at     TIMESTAMPTZ,
    completed_at   TIMESTAMPTZ,
    signed_doc_key TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE signature_fields (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id  UUID NOT NULL REFERENCES signature_requests(id) ON DELETE CASCADE,
    signer_email VARCHAR(255) NOT NULL,
    page_number INTEGER NOT NULL,
    x           FLOAT NOT NULL,
    y           FLOAT NOT NULL,
    width       FLOAT NOT NULL,
    height      FLOAT NOT NULL,
    field_type  VARCHAR(50) NOT NULL DEFAULT 'signature',  -- signature | initials | date | text
    signed_at   TIMESTAMPTZ,
    signature   TEXT  -- base64 encoded signature image
);

-- ──────────────────────────────────────────────
-- Audit Log
-- ──────────────────────────────────────────────
CREATE TABLE audit_logs (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID REFERENCES users(id) ON DELETE SET NULL,
    action      VARCHAR(100) NOT NULL,
    resource    VARCHAR(100),
    resource_id UUID,
    metadata    JSONB NOT NULL DEFAULT '{}',
    ip_address  INET,
    user_agent  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_user ON audit_logs(user_id);
CREATE INDEX idx_audit_created ON audit_logs(created_at DESC);

-- ──────────────────────────────────────────────
-- Updated_at auto-update trigger
-- ──────────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated_at           BEFORE UPDATE ON users             FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_subscriptions_updated_at   BEFORE UPDATE ON subscriptions     FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_documents_updated_at       BEFORE UPDATE ON documents         FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_comments_updated_at        BEFORE UPDATE ON document_comments FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_ai_sessions_updated_at     BEFORE UPDATE ON ai_sessions       FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_usage_quotas_updated_at    BEFORE UPDATE ON usage_quotas      FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ──────────────────────────────────────────────
-- Default quota on user creation
-- ──────────────────────────────────────────────
CREATE OR REPLACE FUNCTION create_user_quota()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO usage_quotas(user_id) VALUES (NEW.id);
    INSERT INTO subscriptions(user_id) VALUES (NEW.id);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_create_user_quota
AFTER INSERT ON users FOR EACH ROW EXECUTE FUNCTION create_user_quota();
