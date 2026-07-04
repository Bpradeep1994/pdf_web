"""
Shared test config. Injects the gateway rate-limit bypass header into EVERY httpx
request so the whole suite can run in one pass without tripping the per-IP limiter.

Patching httpx.Client.request covers both explicit Client(...) usage and the top-level
httpx.get/post/... convenience functions (which create a transient Client internally).
The token must match RATE_LIMIT_BYPASS_TOKEN configured on the gateway.
"""
import os
import httpx

BYPASS_TOKEN = os.getenv("RATE_LIMIT_BYPASS_TOKEN", "ci-test-bypass-9f3a2")

_orig_request = httpx.Client.request


def _request_with_bypass(self, method, url, *args, **kwargs):
    headers = dict(kwargs.get("headers") or {})
    headers.setdefault("x-ratelimit-bypass", BYPASS_TOKEN)
    kwargs["headers"] = headers
    return _orig_request(self, method, url, *args, **kwargs)


httpx.Client.request = _request_with_bypass
