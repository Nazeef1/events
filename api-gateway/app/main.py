"""
EventSphere API Gateway.

The browser only ever talks to this service, at /api/*. Internal
service hostnames (identity-service:8000, etc.) are never exposed to
the client. Responsibilities kept intentionally lightweight per the
project's "no Kong/Traefik unless necessary" constraint:

  - routing: prefix-match /api/<segment>/... to the owning service
  - correlation IDs: every request gets an x-correlation-id, generated
    here if the client didn't send one, forwarded to the downstream
    service and returned in the response for tracing
  - basic rate limiting: sliding window per client IP
  - auth pass-through: the Authorization header is forwarded as-is;
    each downstream service independently verifies the JWT (they all
    trust the same JWT_SECRET) and enforces its own role checks, so
    the gateway does not duplicate that logic
"""
import logging
import time
import uuid

import httpx
from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware

from .config import ROUTES, settings
from .rate_limit import SlidingWindowRateLimiter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("eventsphere.gateway")

app = FastAPI(title="EventSphere API Gateway", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

limiter = SlidingWindowRateLimiter(settings.rate_limit_requests, settings.rate_limit_window_seconds)
auth_limiter = SlidingWindowRateLimiter(settings.auth_rate_limit_requests, settings.rate_limit_window_seconds)
CREDENTIAL_PATHS = {"auth/login", "auth/register"}

HOP_BY_HOP_HEADERS = {"connection", "keep-alive", "transfer-encoding", "content-encoding", "content-length", "host"}


def _resolve_target(path: str) -> tuple[str, str] | None:
    """Longest-prefix match against ROUTES. Returns (base_url, remaining_path)."""
    best: tuple[str, str] | None = None
    for prefix, attr in ROUTES:
        if path == prefix or path.startswith(prefix + "/"):
            if best is None or len(prefix) > len(best[0]):
                best = (prefix, attr)
    if not best:
        return None
    base_url = getattr(settings, best[1])
    return base_url, path


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.service_name}


@app.api_route("/api/{full_path:path}", methods=["GET", "POST", "PATCH", "PUT", "DELETE"])
async def proxy(full_path: str, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    if not limiter.allow(client_ip) or (full_path in CREDENTIAL_PATHS and not auth_limiter.allow(client_ip)):
        return Response(content='{"detail":"Too many requests, slow down."}', status_code=status.HTTP_429_TOO_MANY_REQUESTS, media_type="application/json")

    path = "/" + full_path
    resolved = _resolve_target(path)
    if not resolved:
        return Response(content='{"detail":"No service handles this route."}', status_code=status.HTTP_404_NOT_FOUND, media_type="application/json")
    base_url, downstream_path = resolved

    correlation_id = request.headers.get("x-correlation-id", str(uuid.uuid4()))
    # Never let a browser supply a service identity header, even though only internal routes read it.
    forward_headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP_HEADERS and k.lower() not in ("host", "x-service-token")}
    forward_headers["x-correlation-id"] = correlation_id

    body = await request.body()
    start = time.time()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            upstream = await client.request(
                request.method,
                f"{base_url}{downstream_path}",
                params=request.query_params,
                headers=forward_headers,
                content=body,
            )
    except httpx.RequestError as exc:
        logger.error("Upstream %s unreachable: %s", base_url, exc)
        return Response(content='{"detail":"Upstream service unavailable. Please try again shortly."}', status_code=status.HTTP_502_BAD_GATEWAY, media_type="application/json")

    duration_ms = int((time.time() - start) * 1000)
    logger.info("%s %s -> %s status=%s duration_ms=%s corr_id=%s", request.method, path, base_url, upstream.status_code, duration_ms, correlation_id)

    response_headers = {k: v for k, v in upstream.headers.items() if k.lower() not in HOP_BY_HOP_HEADERS}
    response_headers["x-correlation-id"] = correlation_id
    return Response(content=upstream.content, status_code=upstream.status_code, headers=response_headers, media_type=upstream.headers.get("content-type"))
