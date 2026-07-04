"""
Content-level validation — checks source files for correctness of key fixes.
Run: python tests/validate_content.py
"""
import os, sys, yaml, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
errors   = []
warnings = []


def read(rel_path):
    return open(os.path.join(ROOT, rel_path), encoding="utf-8").read()


# ── 1. Dockerfile COPY ../shared must be gone ─────────────────────────────────
for svc in ["gateway", "auth_service", "pdf_service", "ai_service", "ocr_service", "conversion_service"]:
    df = read(f"backend/{svc}/Dockerfile")
    if "../shared" in df:
        errors.append(f"CRITICAL {svc}/Dockerfile still contains COPY ../shared")

# ── 2. docker-compose build contexts must all be ./backend ───────────────────
dc = yaml.safe_load(open(os.path.join(ROOT, "docker-compose.yml")))
for svc in ["gateway", "auth_service", "pdf_service", "ai_service", "ocr_service", "conversion_service"]:
    ctx = dc["services"][svc].get("build", {}).get("context", "")
    if ctx != "./backend":
        errors.append(f"CRITICAL docker-compose {svc} context={ctx!r} should be './backend'")

# ── 3. MinIO healthcheck must use curl, not mc ───────────────────────────────
hc = str(dc["services"]["minio"].get("healthcheck", {}).get("test", ""))
if "mc ready" in hc:
    errors.append("CRITICAL: MinIO healthcheck still uses 'mc ready'")
if "curl" not in hc and "wget" not in hc:
    errors.append("CRITICAL: MinIO healthcheck should use curl or wget")

# ── 4. next.config.ts must have output: standalone ──────────────────────────
if "standalone" not in read("frontend/next.config.mjs"):
    errors.append("CRITICAL: next.config.ts missing output: 'standalone'")

# ── 5. AIChatPanel null safety ───────────────────────────────────────────────
chat = read("frontend/src/components/editor/AIChatPanel.tsx")
if "string | null" not in chat:
    errors.append("AIChatPanel documentId prop does not accept null")
if "documentId ?? undefined" not in chat:
    errors.append("AIChatPanel does not coerce null documentId before API call")
if "!documentId" not in chat:
    errors.append("AIChatPanel summarize does not guard against null documentId")

# ── 6. AI page must not pass empty string documentId ────────────────────────
ai_page = read("frontend/src/app/(app)/ai/page.tsx")
if 'documentId=""' in ai_page:
    errors.append("ai/page.tsx passes empty string documentId — must be null")

# ── 7. auth_service _make_tokens return type ────────────────────────────────
if "tuple[TokenResponse, str]" not in read("backend/auth_service/routes.py"):
    errors.append("auth_service _make_tokens missing correct return type hint")

# ── 8. OCR routes: Document import must be at top level ─────────────────────
ocr_routes = read("backend/ocr_service/routes.py")
imp_pos = ocr_routes.find("from models import Document")
def_pos = ocr_routes.find("\ndef ")
if imp_pos == -1:
    errors.append("ocr_service/routes.py missing top-level 'from models import Document'")
elif def_pos != -1 and imp_pos > def_pos:
    errors.append("ocr_service/routes.py Document import is INSIDE a function, not at module level")

# ── 9. conversion_service: no unused StreamingResponse ──────────────────────
if "StreamingResponse" in read("backend/conversion_service/routes.py"):
    errors.append("conversion_service/routes.py still imports unused StreamingResponse")

# ── 10. OCR service main.py must initialize DB ──────────────────────────────
if "metadata.create_all" not in read("backend/ocr_service/main.py"):
    errors.append("ocr_service/main.py missing Base.metadata.create_all in lifespan")

# ── 11. sys.path must insert both Docker and local-dev paths ─────────────────
for svc in ["auth_service", "pdf_service", "ai_service", "ocr_service", "conversion_service"]:
    content = read(f"backend/{svc}/main.py")
    if "sys.path.insert" not in content:
        errors.append(f"{svc}/main.py missing sys.path.insert")
    elif '"shared"' not in content and "'shared'" not in content:
        errors.append(f"{svc}/main.py missing Docker-compatible path insert for 'shared'")

# ── 12. Frontend Dockerfile: no bare 'npm ci' without lockfile ───────────────
fe_df = read("frontend/Dockerfile")
if "npm ci" in fe_df and "package-lock.json" not in fe_df and "frozen-lockfile" not in fe_df:
    errors.append("frontend/Dockerfile uses npm ci but doesn't handle missing package-lock.json")

# ── 13. Database migration completeness ──────────────────────────────────────
sql = read("database/migrations/001_init.sql")
for table in ["users", "documents", "ai_sessions", "subscriptions", "usage_quotas", "jobs",
              "document_versions", "document_shares", "signature_requests", "audit_logs"]:
    if f"CREATE TABLE {table}" not in sql:
        errors.append(f"Migration missing table: {table}")

# ── 14. Kubernetes HPA coverage ──────────────────────────────────────────────
hpa = read("kubernetes/hpa.yaml")
for svc in ["gateway", "pdf-service", "ai-service", "ocr-service"]:
    if svc not in hpa:
        warnings.append(f"HPA missing for {svc}")

# ── 15. package.json has required deps ───────────────────────────────────────
pkg = json.loads(read("frontend/package.json"))
all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
for dep in ["next", "react", "pdfjs-dist", "fabric", "zustand", "tailwindcss", "typescript", "stripe"]:
    if dep not in all_deps:
        errors.append(f"frontend/package.json missing dependency: {dep}")

# ── 16. tsconfig strict mode ─────────────────────────────────────────────────
ts = json.loads(read("frontend/tsconfig.json"))
if not ts.get("compilerOptions", {}).get("strict"):
    errors.append("frontend/tsconfig.json must have strict: true")

# ── Report ────────────────────────────────────────────────────────────────────
total = len(errors) + len(warnings)
print(f"\n{'='*60}")
print(f"Content Validation: {len(errors)} errors, {len(warnings)} warnings")
print(f"{'='*60}")
if errors:
    for e in errors:
        print(f"  FAIL  {e}")
if warnings:
    for w in warnings:
        print(f"  WARN  {w}")
if not errors and not warnings:
    print("  All checks PASSED - OK")
print(f"{'='*60}\n")
sys.exit(1 if errors else 0)
