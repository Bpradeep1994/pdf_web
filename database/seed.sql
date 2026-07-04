-- Seed default RBAC roles + permissions. Idempotent: safe to run repeatedly.
-- Run: psql "$DATABASE_URL" -f database/seed.sql
--   (or via the one-off migration container on the pdf_editor network)

-- ── Roles ────────────────────────────────────────────────────────────────────
INSERT INTO roles (name, description) VALUES
    ('admin',  'Full platform administration'),
    ('editor', 'Create and edit own documents'),
    ('viewer', 'Read-only access + comments')
ON CONFLICT (name) DO NOTHING;

-- ── Permissions ──────────────────────────────────────────────────────────────
INSERT INTO permissions (name, description) VALUES
    ('document:read',     'View documents'),
    ('document:write',    'Create/edit documents'),
    ('document:delete',   'Delete documents'),
    ('document:share',    'Share documents'),
    ('document:convert',  'Convert documents'),
    ('comment:write',     'Add comments'),
    ('signature:request', 'Request signatures'),
    ('billing:manage',    'Manage own billing'),
    ('admin:users',       'Manage users'),
    ('admin:billing',     'View revenue/subscriptions'),
    ('admin:audit',       'View audit logs')
ON CONFLICT (name) DO NOTHING;

-- ── Role → permission mappings ───────────────────────────────────────────────
-- admin: everything
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
WHERE r.name = 'admin'
ON CONFLICT DO NOTHING;

-- editor: document:* + comment + signature + billing
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r JOIN permissions p ON p.name IN (
    'document:read','document:write','document:delete','document:share',
    'document:convert','comment:write','signature:request','billing:manage')
WHERE r.name = 'editor'
ON CONFLICT DO NOTHING;

-- viewer: read + comment
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r JOIN permissions p ON p.name IN ('document:read','comment:write')
WHERE r.name = 'viewer'
ON CONFLICT DO NOTHING;

-- ── Backfill: map existing users to a role row matching their enum role ───────
INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id FROM users u
JOIN roles r ON r.name = CASE WHEN u.role = 'admin' THEN 'admin' ELSE 'editor' END
ON CONFLICT DO NOTHING;
