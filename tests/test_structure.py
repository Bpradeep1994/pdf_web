"""
Structural validation tests — run on any Python version without installing service deps.
Verifies: required files exist, YAML is valid, requirements are complete, no obvious misconfig.
"""
import os
import re
import yaml  # stdlib yaml via pyyaml — install separately if needed
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def path(*parts):
    return os.path.join(ROOT, *parts)


# ── File existence ────────────────────────────────────────────────────────────

REQUIRED_FILES = [
    "docker-compose.yml",
    ".env.example",
    "database/migrations/001_init.sql",
    "backend/shared/database.py",
    "backend/shared/s3.py",
    "backend/shared/queue.py",
    "backend/shared/security.py",
    "backend/gateway/main.py",
    "backend/gateway/Dockerfile",
    "backend/gateway/requirements.txt",
    "backend/auth_service/main.py",
    "backend/auth_service/routes.py",
    "backend/auth_service/models.py",
    "backend/auth_service/schemas.py",
    "backend/auth_service/Dockerfile",
    "backend/auth_service/requirements.txt",
    "backend/pdf_service/main.py",
    "backend/pdf_service/routes.py",
    "backend/pdf_service/models.py",
    "backend/pdf_service/Dockerfile",
    "backend/pdf_service/requirements.txt",
    # ai_service removed (AI feature dropped)
    "backend/ocr_service/main.py",
    "backend/ocr_service/routes.py",
    "backend/ocr_service/models.py",
    "backend/ocr_service/Dockerfile",
    "backend/ocr_service/requirements.txt",
    "backend/conversion_service/main.py",
    "backend/conversion_service/routes.py",
    "backend/conversion_service/Dockerfile",
    "backend/conversion_service/requirements.txt",
    "frontend/package.json",
    "frontend/tsconfig.json",
    "frontend/tailwind.config.ts",
    "frontend/next.config.mjs",
    "frontend/Dockerfile",
    "frontend/src/app/layout.tsx",
    "frontend/src/app/page.tsx",
    "frontend/src/app/globals.css",
    "frontend/src/app/(auth)/login/page.tsx",
    "frontend/src/app/(auth)/register/page.tsx",
    "frontend/src/app/(app)/layout.tsx",
    "frontend/src/app/(app)/dashboard/page.tsx",
    "frontend/src/app/(app)/editor/[id]/page.tsx",
    "frontend/src/app/(app)/projects/page.tsx",
    "frontend/src/app/(app)/billing/page.tsx",
    "frontend/src/app/(app)/admin/page.tsx",
    "frontend/src/app/(app)/settings/page.tsx",
    "frontend/src/lib/api.ts",
    "frontend/src/lib/auth.ts",
    "frontend/src/lib/utils.ts",
    "frontend/src/components/layout/Sidebar.tsx",
    "frontend/src/components/dashboard/UploadButton.tsx",
    "frontend/src/components/editor/PDFViewer.tsx",
    "frontend/src/components/editor/Toolbar.tsx",
    "frontend/src/components/editor/CommentsPanel.tsx",
    "frontend/src/components/editor/SignaturePanel.tsx",
    "frontend/src/components/editor/ImageLayer.tsx",
    "frontend/src/components/editor/VersionHistory.tsx",
    "kubernetes/namespace.yaml",
    "kubernetes/configmap.yaml",
    "kubernetes/secrets.yaml",
    "kubernetes/deployments.yaml",
    "kubernetes/services.yaml",
    "kubernetes/ingress.yaml",
    "kubernetes/hpa.yaml",
]


@pytest.mark.parametrize("rel_path", REQUIRED_FILES)
def test_required_file_exists(rel_path):
    full = path(rel_path)
    assert os.path.isfile(full), f"Missing required file: {rel_path}"


@pytest.mark.parametrize("rel_path", REQUIRED_FILES)
def test_required_file_not_empty(rel_path):
    full = path(rel_path)
    if not os.path.isfile(full):
        pytest.skip("File missing — covered by existence test")
    assert os.path.getsize(full) > 0, f"File is empty: {rel_path}"


# ── Docker Compose YAML validity ──────────────────────────────────────────────

def test_docker_compose_is_valid_yaml():
    try:
        import yaml as _yaml
    except ImportError:
        pytest.skip("pyyaml not installed")
    with open(path("docker-compose.yml")) as f:
        data = _yaml.safe_load(f)
    assert data is not None
    assert "services" in data
    assert "volumes" in data


def test_docker_compose_services_present():
    try:
        import yaml as _yaml
    except ImportError:
        pytest.skip("pyyaml not installed")
    with open(path("docker-compose.yml")) as f:
        data = _yaml.safe_load(f)
    services = set(data["services"].keys())
    expected = {
        "postgres", "redis", "rabbitmq", "minio",
        "gateway", "auth_service", "pdf_service",
        "ocr_service", "conversion_service", "frontend",
    }
    missing = expected - services
    assert not missing, f"Missing services in docker-compose.yml: {missing}"


def test_docker_compose_build_contexts_use_backend_root():
    try:
        import yaml as _yaml
    except ImportError:
        pytest.skip("pyyaml not installed")
    with open(path("docker-compose.yml")) as f:
        data = _yaml.safe_load(f)
    backend_services = ["gateway", "auth_service", "pdf_service", "ocr_service", "conversion_service"]
    for svc in backend_services:
        build = data["services"][svc].get("build", {})
        ctx = build.get("context", "")
        assert ctx == "./backend", (
            f"Service '{svc}' has wrong build context '{ctx}' — must be './backend'"
        )


def test_minio_healthcheck_not_using_mc():
    try:
        import yaml as _yaml
    except ImportError:
        pytest.skip("pyyaml not installed")
    with open(path("docker-compose.yml")) as f:
        data = _yaml.safe_load(f)
    hc = data["services"]["minio"].get("healthcheck", {})
    test_cmd = str(hc.get("test", ""))
    assert "mc ready" not in test_cmd, "MinIO healthcheck still uses 'mc ready' — mc is not installed in the image"
    assert "curl" in test_cmd or "wget" in test_cmd, "MinIO healthcheck should use curl or wget"


# ── Dockerfile correctness ────────────────────────────────────────────────────

BACKEND_SERVICES = ["gateway", "auth_service", "pdf_service", "ocr_service", "conversion_service"]


@pytest.mark.parametrize("svc", BACKEND_SERVICES)
def test_dockerfile_no_parent_relative_copy(svc):
    """COPY ../shared is invalid when context is ./backend — must be COPY shared/"""
    df_path = path("backend", svc, "Dockerfile")
    if not os.path.isfile(df_path):
        pytest.skip("Dockerfile missing")
    content = open(df_path).read()
    assert "COPY ../shared" not in content, (
        f"{svc}/Dockerfile still contains 'COPY ../shared' which is outside the build context"
    )


@pytest.mark.parametrize("svc", ["auth_service", "pdf_service", "ocr_service", "conversion_service"])
def test_dockerfile_copies_shared(svc):
    df_path = path("backend", svc, "Dockerfile")
    if not os.path.isfile(df_path):
        pytest.skip("Dockerfile missing")
    content = open(df_path).read()
    assert "COPY shared/" in content, f"{svc}/Dockerfile must copy 'shared/' directory"


def test_frontend_dockerfile_has_standalone_copy():
    content = open(path("frontend", "Dockerfile")).read()
    assert ".next/standalone" in content, "Frontend Dockerfile must copy .next/standalone"


def test_frontend_next_config_has_standalone_output():
    content = open(path("frontend", "next.config.mjs")).read()
    assert 'output: "standalone"' in content or "output: 'standalone'" in content, (
        "next.config.mjs must have output: 'standalone' for the multi-stage Docker build"
    )


# ── sys.path fixes in main.py files ──────────────────────────────────────────

@pytest.mark.parametrize("svc", [s for s in BACKEND_SERVICES if s != "gateway"])
def test_main_py_inserts_shared_path(svc):
    """Gateway doesn't import from shared/ so it has no sys.path setup — that's correct."""
    main_path = path("backend", svc, "main.py")
    if not os.path.isfile(main_path):
        pytest.skip("main.py missing")
    content = open(main_path).read()
    assert 'sys.path.insert' in content, f"{svc}/main.py must insert shared into sys.path"
    assert '"shared"' in content or "'shared'" in content, (
        f"{svc}/main.py must include the Docker-compatible shared path (not just ../shared)"
    )


# ── Requirements completeness ─────────────────────────────────────────────────

REQUIRED_DEPS = {
    "auth_service": ["fastapi", "uvicorn", "sqlalchemy", "asyncpg", "python-jose", "bcrypt", "httpx", "pyotp", "qrcode", "pydantic"],
    "pdf_service":  ["fastapi", "uvicorn", "sqlalchemy", "asyncpg", "pymupdf", "boto3", "aio-pika", "pydantic"],
    "ocr_service":  ["fastapi", "uvicorn", "pymupdf", "pytesseract", "Pillow", "boto3", "pydantic"],
    "conversion_service": ["fastapi", "uvicorn", "pymupdf", "Pillow", "boto3", "pydantic"],
    "gateway":      ["fastapi", "uvicorn", "httpx", "redis"],
}


@pytest.mark.parametrize("svc,deps", REQUIRED_DEPS.items())
def test_requirements_has_deps(svc, deps):
    req_path = path("backend", svc, "requirements.txt")
    if not os.path.isfile(req_path):
        pytest.skip("requirements.txt missing")
    content = open(req_path).read().lower()
    missing = [d for d in deps if d.lower().split("[")[0] not in content]
    assert not missing, f"{svc}/requirements.txt is missing: {missing}"


# ── Python source content checks ──────────────────────────────────────────────

def test_auth_routes_make_tokens_return_type():
    content = open(path("backend", "auth_service", "routes.py")).read()
    assert "tuple[TokenResponse, str]" in content, (
        "_make_tokens must have correct return type hint: tuple[TokenResponse, str]"
    )


def test_ocr_routes_has_top_level_model_import():
    content = open(path("backend", "ocr_service", "routes.py")).read()
    # Import should appear before any function definition
    import_pos = content.find("from models import Document")
    first_def  = content.find("\ndef ")
    assert import_pos != -1, "ocr_service/routes.py must import Document at top level"
    assert import_pos < first_def, "Document import must be at module level, not inside a function"


def test_conversion_routes_no_streaming_response_import():
    content = open(path("backend", "conversion_service", "routes.py")).read()
    assert "from fastapi.responses import StreamingResponse" not in content, (
        "conversion_service/routes.py has unused StreamingResponse import"
    )


# ── Database migration completeness ──────────────────────────────────────────

def test_migration_has_all_tables():
    sql = open(path("database", "migrations", "001_init.sql")).read()
    required_tables = [
        "CREATE TABLE users",
        "CREATE TABLE refresh_tokens",
        "CREATE TABLE subscriptions",
        "CREATE TABLE documents",
        "CREATE TABLE document_versions",
        "CREATE TABLE document_shares",
        "CREATE TABLE document_comments",
        "CREATE TABLE jobs",
        "CREATE TABLE ai_sessions",
        "CREATE TABLE ai_messages",
        "CREATE TABLE signature_requests",
        "CREATE TABLE audit_logs",
        "CREATE TABLE usage_quotas",
    ]
    missing = [t for t in required_tables if t not in sql]
    assert not missing, f"Migration missing table definitions: {missing}"


def test_migration_has_triggers():
    sql = open(path("database", "migrations", "001_init.sql")).read()
    assert "update_updated_at" in sql, "Migration must include updated_at trigger function"
    assert "create_user_quota" in sql, "Migration must include user quota creation trigger"


# ── Kubernetes ────────────────────────────────────────────────────────────────

K8S_FILES = ["namespace.yaml", "configmap.yaml", "secrets.yaml",
             "deployments.yaml", "services.yaml", "ingress.yaml", "hpa.yaml"]


@pytest.mark.parametrize("fname", K8S_FILES)
def test_k8s_file_is_valid_yaml(fname):
    try:
        import yaml as _yaml
    except ImportError:
        pytest.skip("pyyaml not installed")
    fpath = path("kubernetes", fname)
    if not os.path.isfile(fpath):
        pytest.skip("File missing")
    with open(fpath) as f:
        docs = list(_yaml.safe_load_all(f))
    assert len(docs) > 0, f"{fname} produced no YAML documents"
    for doc in docs:
        if doc is not None:
            assert "apiVersion" in doc, f"{fname} document missing apiVersion"


def test_k8s_deployments_cover_all_services():
    try:
        import yaml as _yaml
    except ImportError:
        pytest.skip("pyyaml not installed")
    with open(path("kubernetes", "deployments.yaml")) as f:
        docs = [d for d in _yaml.safe_load_all(f) if d and d.get("kind") == "Deployment"]
    names = {d["metadata"]["name"] for d in docs}
    expected = {"frontend", "gateway", "auth-service", "pdf-service", "ocr-service", "conversion-service"}
    missing = expected - names
    assert not missing, f"Deployments missing for: {missing}"


def test_k8s_hpa_covers_key_services():
    try:
        import yaml as _yaml
    except ImportError:
        pytest.skip("pyyaml not installed")
    with open(path("kubernetes", "hpa.yaml")) as f:
        docs = [d for d in _yaml.safe_load_all(f) if d and d.get("kind") == "HorizontalPodAutoscaler"]
    targets = {d["spec"]["scaleTargetRef"]["name"] for d in docs}
    assert "gateway" in targets
    assert "pdf-service" in targets


# ── Frontend package.json checks ─────────────────────────────────────────────

def test_frontend_package_json_has_key_deps():
    import json
    with open(path("frontend", "package.json")) as f:
        pkg = json.load(f)
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    required = ["next", "react", "pdfjs-dist", "fabric", "zustand",
                "@tanstack/react-query", "stripe", "react-dropzone",
                "tailwindcss", "typescript"]
    missing = [d for d in required if d not in deps]
    assert not missing, f"package.json missing deps: {missing}"


def test_frontend_tsconfig_strict_mode():
    import json
    with open(path("frontend", "tsconfig.json")) as f:
        ts = json.load(f)
    assert ts["compilerOptions"].get("strict") is True, "tsconfig.json must have strict: true"
